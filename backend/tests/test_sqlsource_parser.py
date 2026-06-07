"""SQL source parser tests."""

from __future__ import annotations

from app.gdp.datagen.config.common.models import InputFieldType
from app.gdp.datagen.config.sqlsource.models import SqlSourceParameter
from app.gdp.datagen.config.sqlsource.parser import parse_sql_source


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
    assert result.normalizedSql == "SELECT * FROM t_user WHERE user_name = ?"
    assert [table.tableName for table in result.tables] == ["t_user"]
    assert [param.name for param in result.parameters] == ["userName"]


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

    assert result.normalizedSql == "SELECT id, user_name FROM t_user WHERE id IN (?,?,?)"
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

    assert result.normalizedSql == "SELECT * FROM t_user WHERE id = ?"
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
    assert result.normalizedSql == "UPDATE t_user SET user_name = ?, updated_at = now() WHERE id = ?"
    assert [param.name for param in result.parameters] == ["id", "userName"]
