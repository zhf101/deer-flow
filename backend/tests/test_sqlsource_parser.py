"""SQL 配置解析器测试。"""

from __future__ import annotations

from app.gdp.datagen.config.common.models import InputFieldType
from app.gdp.datagen.config.sqlsource.models import (
    SqlSourceConfig,
    SqlSourceParameter,
    SqlSourceTableMeta,
)
from app.gdp.datagen.config.sqlsource.parser import parse_sql_source
from app.gdp.datagen.config.sqlsource.service import SqlSourceService


def test_parse_plain_sql_extracts_metadata_and_keeps_existing_parameter_definition():
    result = parse_sql_source(
        """
        select u.id, u.user_name as userName, o.amount
        from t_user u
        join t_order o on o.user_id = u.id
        where u.id = :userId and o.status = #{status}
        """,
        parameters=[
            SqlSourceParameter(
                name="userId",
                type=InputFieldType.NUMBER,
                required=False,
                description="existing definition",
            )
        ],
    )

    assert result.operation == "SELECT"
    assert result.normalizedSql.startswith("select u.id")
    assert {(table.tableName, table.alias) for table in result.tables} == {
        ("t_user", "u"),
        ("t_order", "o"),
    }
    assert ("user_name", "u", "userName") in {
        (field.fieldName, field.sourceTable, field.alias) for field in result.resultFields
    }
    assert ("status", "o", "status") in {
        (field.fieldName, field.sourceTable, field.paramName) for field in result.conditionFields
    }
    params = {param.name: param for param in result.parameters}
    assert params["userId"].type == InputFieldType.NUMBER
    assert params["userId"].required is False
    assert params["status"].type == InputFieldType.STRING


def test_parse_plain_sql_normalizes_mybatis_style_placeholders_to_named_parameters():
    result = parse_sql_source(
        """
        select * from t_user where status = #{status} and tenant_id = ${tenantId}
        """
    )

    assert (
        result.normalizedSql
        == "select * from t_user where status = :status and tenant_id = :tenantId"
    )
    assert [param.name for param in result.parameters] == ["status", "tenantId"]


def test_parse_mybatis_where_if_renders_executable_sql_template():
    result = parse_sql_source(
        """
        <select id="selectByCondition">
            SELECT *
            FROM t_user
            <where>
                <if test="userName != null">
                    AND user_name = #{userName}
                </if>
            </where>
        </select>
        """
    )

    assert result.operation == "SELECT"
    assert result.normalizedSql == "SELECT * FROM t_user WHERE user_name = :userName"
    assert [table.tableName for table in result.tables] == ["t_user"]
    assert [param.name for param in result.parameters] == ["userName"]


def test_parse_mybatis_condition_fields_keep_sql_parameter_order():
    result = parse_sql_source(
        """
        <select id="queryByOrder">
            SELECT *
            FROM t_user
            WHERE b_col = #{zParam}
              AND a_col = #{aParam}
        </select>
        """
    )

    condition_params = {field.fieldName: field.paramName for field in result.conditionFields}
    assert condition_params["b_col"] == "zParam"
    assert condition_params["a_col"] == "aParam"


def test_parse_mybatis_foreach_expands_collection_with_sample_params():
    result = parse_sql_source(
        """
        <select id="selectByIds">
            SELECT id, user_name
            FROM t_user
            WHERE id IN
            <foreach collection="ids" item="id" open="(" separator="," close=")">
                #{id}
            </foreach>
        </select>
        """,
        parameters=[
            SqlSourceParameter(
                name="ids",
                type=InputFieldType.ARRAY,
                defaultValue=[1, 2, 3],
            )
        ],
    )

    assert result.normalizedSql == "SELECT id, user_name FROM t_user WHERE id IN (:ids,:ids,:ids)"
    assert [param.name for param in result.parameters] == ["ids"]


def test_parse_mybatis_choose_uses_first_matching_branch():
    result = parse_sql_source(
        """
        <select id="selectOne">
            SELECT * FROM t_user
            <where>
                <choose>
                    <when test="id != null">
                        AND id = #{id}
                    </when>
                    <otherwise>
                        AND deleted = 0
                    </otherwise>
                </choose>
            </where>
        </select>
        """,
        parameters=[SqlSourceParameter(name="id", type=InputFieldType.NUMBER, defaultValue=10)],
    )

    assert result.normalizedSql == "SELECT * FROM t_user WHERE id = :id"
    assert [param.name for param in result.parameters] == ["id"]


def test_parse_mybatis_set_trims_trailing_comma():
    result = parse_sql_source(
        """
        <update id="updateUser">
            UPDATE t_user
            <set>
                <if test="userName != null">
                    user_name = #{userName},
                </if>
                updated_at = now(),
            </set>
            WHERE id = #{id}
        </update>
        """
    )

    assert result.operation == "UPDATE"
    assert result.normalizedSql == "UPDATE t_user SET user_name = :userName, updated_at = now() WHERE id = :id"
    assert [param.name for param in result.parameters] == ["id", "userName"]


def test_save_preparation_fills_missing_metadata_without_overwriting_existing_descriptions():
    config = SqlSourceConfig(
        sourceCode="queryUser",
        sourceName="查询用户",
        sysCode="USER",
        datasourceCode="userDb",
        operation="SELECT",
        sqlText="select id, user_name from t_user where id = :userId",
        normalizedSql="select id, user_name from t_user where id = :userId",
        tables=[
            SqlSourceTableMeta(
                id="table_0_t_user",
                tableName="t_user",
                alias="",
                description="用户表",
            )
        ],
    )

    prepared = SqlSourceService._ensure_analysis_metadata(config)

    assert prepared.tables[0].description == "用户表"
    assert [field.fieldName for field in prepared.resultFields] == ["id", "user_name"]
    assert prepared.conditionFields[0].paramName == "userId"
