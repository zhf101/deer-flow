"""Tests for the MyBatis XML → AST → SQL → sqlglot parsing pipeline."""

from __future__ import annotations

import pytest

from app.gdp.datagen.config.sqlsource.parser import parse_sql_source
from app.gdp.datagen.config.sqlsource.parsers.ast import (
    ChooseNode,
    ForeachNode,
    IfNode,
    MapperNode,
    OtherwiseNode,
    SetNode,
    StatementNode,
    TextNode,
    TrimNode,
    WhenNode,
    WhereNode,
)
from app.gdp.datagen.config.sqlsource.parsers.mybatis_parser import parse_mybatis_xml
from app.gdp.datagen.config.sqlsource.parsers.mybatis_renderer import render


# ── AST parsing tests ───────────────────────────────────────────────────


class TestMyBatisParser:
    def test_single_statement(self):
        xml = '<select id="q">SELECT 1</select>'
        ast = parse_mybatis_xml(xml)
        assert isinstance(ast, StatementNode)
        assert ast.statement_type == "select"
        assert ast.statement_id == "q"

    def test_statement_with_if(self):
        xml = """
        <select id="q">
            SELECT * FROM t
            <where>
                <if test="x != null">AND x = #{x}</if>
            </where>
        </select>
        """
        ast = parse_mybatis_xml(xml)
        assert isinstance(ast, StatementNode)
        # Should have TextNode + WhereNode
        types = [type(c) for c in ast.children]
        assert WhereNode in types
        where = [c for c in ast.children if isinstance(c, WhereNode)][0]
        assert any(isinstance(c, IfNode) for c in where.children)

    def test_foreach(self):
        xml = """
        <select id="q">
            SELECT * FROM t WHERE id IN
            <foreach collection="ids" item="id" open="(" separator="," close=")">
                #{id}
            </foreach>
        </select>
        """
        ast = parse_mybatis_xml(xml)
        foreach_nodes = [c for c in ast.children if isinstance(c, ForeachNode)]
        assert len(foreach_nodes) == 1
        f = foreach_nodes[0]
        assert f.collection == "ids"
        assert f.item == "id"
        assert f.open == "("
        assert f.separator == ","
        assert f.close == ")"

    def test_choose_when_otherwise(self):
        xml = """
        <select id="q">
            SELECT * FROM t
            <where>
                <choose>
                    <when test="a != null">AND a = #{a}</when>
                    <when test="b != null">AND b = #{b}</when>
                    <otherwise>AND c = 1</otherwise>
                </choose>
            </where>
        </select>
        """
        ast = parse_mybatis_xml(xml)
        where = [c for c in ast.children if isinstance(c, WhereNode)][0]
        choose = [c for c in where.children if isinstance(c, ChooseNode)][0]
        assert len(choose.when_clauses) == 2
        assert choose.otherwise is not None

    def test_set_node(self):
        xml = """
        <update id="u">
            UPDATE t
            <set>
                <if test="a != null">a = #{a},</if>
                <if test="b != null">b = #{b},</if>
            </set>
            WHERE id = #{id}
        </update>
        """
        ast = parse_mybatis_xml(xml)
        assert ast.statement_type == "update"
        set_nodes = [c for c in ast.children if isinstance(c, SetNode)]
        assert len(set_nodes) == 1

    def test_trim_node(self):
        xml = """
        <select id="q">
            SELECT * FROM t
            <trim prefix="WHERE" prefixOverrides="AND|OR">
                <if test="x != null">AND x = #{x}</if>
            </trim>
        </select>
        """
        ast = parse_mybatis_xml(xml)
        trim_nodes = [c for c in ast.children if isinstance(c, TrimNode)]
        assert len(trim_nodes) == 1
        assert trim_nodes[0].prefix == "WHERE"
        assert trim_nodes[0].prefix_overrides == ["AND", "OR"]

    def test_full_mapper_xml(self):
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <mapper namespace="com.example.UserMapper">
            <select id="queryUser">SELECT * FROM t_user WHERE id = #{id}</select>
            <insert id="createUser">INSERT INTO t_user (name) VALUES (#{name})</insert>
        </mapper>
        """
        ast = parse_mybatis_xml(xml)
        assert isinstance(ast, MapperNode)
        assert ast.namespace == "com.example.UserMapper"
        assert len(ast.statements) == 2
        assert ast.statements[0].statement_type == "select"
        assert ast.statements[1].statement_type == "insert"

    def test_invalid_xml_raises(self):
        with pytest.raises((ValueError, Exception)):
            parse_mybatis_xml("NOT XML AT ALL")


# ── AST rendering tests ────────────────────────────────────────────────


class TestMyBatisRenderer:
    def test_render_if_true(self):
        xml = '<select id="q">SELECT * FROM t<if test="x != null"> WHERE x = #{x}</if></select>'
        ast = parse_mybatis_xml(xml)
        result = render(ast, values={"x": "hello"})
        assert "WHERE x = #{x}" in result.sql
        assert "x" in result.referenced_params

    def test_render_if_false(self):
        xml = '<select id="q">SELECT * FROM t<if test="x != null"> WHERE x = #{x}</if></select>'
        ast = parse_mybatis_xml(xml)
        result = render(ast, values={"x": None})
        assert "WHERE" not in result.sql
        assert len(result.referenced_params) == 0

    def test_render_if_unknown_ognl_includes_branch(self):
        xml = '<select id="q">SELECT * FROM t<if test="obj.field != null"> WHERE x = 1</if></select>'
        ast = parse_mybatis_xml(xml)
        # all_branches=True is the correct way to include all conditional branches
        result = render(ast, values={}, all_branches=True)
        assert "WHERE x = 1" in result.sql

    def test_render_where_strips_leading_and(self):
        xml = """
        <select id="q">SELECT * FROM t
        <where>
            <if test="true">AND x = 1</if>
        </where>
        </select>
        """
        ast = parse_mybatis_xml(xml)
        result = render(ast, values={}, all_branches=True)
        assert "WHERE x = 1" in result.sql
        assert "WHERE AND" not in result.sql

    def test_render_where_empty_when_no_conditions(self):
        xml = """
        <select id="q">SELECT * FROM t
        <where>
            <if test="x != null">AND x = #{x}</if>
        </where>
        </select>
        """
        ast = parse_mybatis_xml(xml)
        result = render(ast, values={"x": None})
        assert "WHERE" not in result.sql

    def test_render_set_strips_trailing_comma(self):
        xml = """
        <update id="u">UPDATE t
        <set>
            a = 1,
            b = 2,
        </set>
        WHERE id = 1
        </update>
        """
        ast = parse_mybatis_xml(xml)
        result = render(ast, values={}, all_branches=True)
        assert "SET a = 1, b = 2" in result.sql
        assert result.sql.rstrip().endswith("WHERE id = 1")

    def test_render_foreach(self):
        xml = """
        <select id="q">SELECT * FROM t WHERE id IN
        <foreach collection="ids" item="id" open="(" separator="," close=")">
            #{id}
        </foreach>
        </select>
        """
        ast = parse_mybatis_xml(xml)
        result = render(ast, values={"ids": [1, 2, 3]})
        assert "(#{id},#{id},#{id})" in result.sql
        assert "ids" in result.referenced_params

    def test_render_foreach_analysis_mode(self):
        xml = """
        <select id="q">SELECT * FROM t WHERE id IN
        <foreach collection="ids" item="id" open="(" separator="," close=")">
            #{id}
        </foreach>
        </select>
        """
        ast = parse_mybatis_xml(xml)
        result = render(ast, all_branches=True)
        assert "(#{id})" in result.sql

    def test_render_choose_first_when(self):
        xml = """
        <select id="q">SELECT * FROM t WHERE
        <choose>
            <when test="a != null">a = #{a}</when>
            <when test="b != null">b = #{b}</when>
            <otherwise>c = 1</otherwise>
        </choose>
        </select>
        """
        ast = parse_mybatis_xml(xml)
        result = render(ast, values={"a": "yes", "b": None})
        assert "a = #{a}" in result.sql
        assert "b = #{b}" not in result.sql

    def test_render_choose_otherwise(self):
        xml = """
        <select id="q">SELECT * FROM t WHERE
        <choose>
            <when test="a != null">a = #{a}</when>
            <otherwise>c = 1</otherwise>
        </choose>
        </select>
        """
        ast = parse_mybatis_xml(xml)
        result = render(ast, values={"a": None})
        assert "c = 1" in result.sql

    def test_render_all_branches_includes_everything(self):
        xml = """
        <select id="q">SELECT * FROM t
        <where>
            <if test="a != null">AND a = #{a}</if>
            <if test="b != null">AND b = #{b}</if>
            <choose>
                <when test="c != null">AND c = #{c}</when>
                <otherwise>AND d = #{d}</otherwise>
            </choose>
        </where>
        </select>
        """
        ast = parse_mybatis_xml(xml)
        result = render(ast, all_branches=True)
        assert "#{a}" in result.sql
        assert "#{b}" in result.sql
        assert "#{c}" in result.sql
        assert "#{d}" in result.sql
        assert result.referenced_params >= {"a", "b", "c", "d"}


# ── Full pipeline tests (XML → AST → SQL → sqlglot) ────────────────────


class TestFullPipeline:
    def test_select_with_dynamic_where(self):
        xml = """
        <select id="selectByCondition">
            SELECT id, user_name, email
            FROM t_user u
            <where>
                <if test="userName != null">AND u.user_name = #{userName}</if>
                <if test="email != null">AND u.email = #{email}</if>
            </where>
        </select>
        """
        r = parse_sql_source(xml)
        assert r.operation == "SELECT"
        assert any(t.tableName == "t_user" and t.alias == "u" for t in r.tables)
        assert any(f.fieldName == "user_name" for f in r.resultFields)
        param_names = {p.name for p in r.parameters}
        assert "userName" in param_names
        assert "email" in param_names

    def test_update_with_set(self):
        xml = """
        <update id="updateUser">
            UPDATE t_user
            <set>
                <if test="userName != null">user_name = #{userName},</if>
                <if test="email != null">email = #{email},</if>
            </set>
            WHERE id = #{userId}
        </update>
        """
        r = parse_sql_source(xml)
        assert r.operation == "UPDATE"
        assert any(t.tableName == "t_user" for t in r.tables)
        param_names = {p.name for p in r.parameters}
        assert "userId" in param_names
        assert "userName" in param_names
        assert "email" in param_names

    def test_insert(self):
        xml = """
        <insert id="createUser">
            INSERT INTO t_user (user_name, email, status)
            VALUES (#{userName}, #{email}, #{status})
        </insert>
        """
        r = parse_sql_source(xml)
        assert r.operation == "INSERT"
        assert any(t.tableName == "t_user" for t in r.tables)
        param_names = {p.name for p in r.parameters}
        assert param_names >= {"userName", "email", "status"}

    def test_foreach_in_where(self):
        xml = """
        <select id="selectByIds">
            SELECT * FROM t_order
            WHERE id IN
            <foreach collection="ids" item="id" open="(" separator="," close=")">
                #{id}
            </foreach>
        </select>
        """
        r = parse_sql_source(xml)
        assert r.operation == "SELECT"
        assert any(t.tableName == "t_order" for t in r.tables)
        assert any(p.name == "ids" for p in r.parameters)

    def test_choose_with_set(self):
        xml = """
        <update id="updateUser">
            UPDATE t_user
            <set>
                <choose>
                    <when test="updateType == 'name'">user_name = #{userName},</when>
                    <when test="updateType == 'email'">email = #{email},</when>
                    <otherwise>status = #{status},</otherwise>
                </choose>
            </set>
            WHERE id = #{userId}
        </update>
        """
        r = parse_sql_source(xml)
        assert r.operation == "UPDATE"
        param_names = {p.name for p in r.parameters}
        # all_branches=True should discover all params
        assert param_names >= {"userName", "email", "status", "userId"}

    def test_plain_sql_fallback(self):
        sql = "SELECT a.id, a.name FROM account a WHERE a.status = :status"
        r = parse_sql_source(sql)
        assert r.operation == "SELECT"
        assert any(t.tableName == "account" for t in r.tables)
        assert any(p.name == "status" for p in r.parameters)

    def test_existing_parameters_preserved(self):
        from app.gdp.datagen.config.sqlsource.models import SqlSourceParameter

        existing = [
            SqlSourceParameter(name="userName", type="string", required=True, description="用户名"),
        ]
        xml = """
        <select id="q">
            SELECT * FROM t WHERE name = #{userName}
        </select>
        """
        r = parse_sql_source(xml, parameters=existing)
        user_param = next(p for p in r.parameters if p.name == "userName")
        assert user_param.description == "用户名"

    def test_mybatis_with_join(self):
        xml = """
        <select id="queryOrders">
            SELECT o.id, o.amount, u.user_name
            FROM t_order o
            INNER JOIN t_user u ON o.user_id = u.id
            <where>
                <if test="status != null">AND o.status = #{status}</if>
                <if test="userId != null">AND o.user_id = #{userId}</if>
            </where>
        </select>
        """
        r = parse_sql_source(xml)
        table_names = {t.tableName for t in r.tables}
        assert "t_order" in table_names
        assert "t_user" in table_names
