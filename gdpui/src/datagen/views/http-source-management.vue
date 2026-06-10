<template>
  <div class="http-source-mgmt">
    <!-- ── List View ── -->
    <template v-if="!editing">
      <div class="page-header">
        <h2>HTTP 接口配置</h2>
        <el-button type="primary" size="small" @click="handleNew">
          <font-awesome-icon icon="plus" /> 新增接口
        </el-button>
      </div>

      <div class="filters-bar">
        <el-select v-model="methodFilter" placeholder="请求方式" clearable size="small" @change="onFilterChange">
          <el-option label="全部方式" value="" />
          <el-option label="GET" value="GET" />
          <el-option label="POST" value="POST" />
        </el-select>
        <el-select v-model="sysCodeFilter" placeholder="所属系统" clearable size="small" @change="onFilterChange">
          <el-option label="全部系统" value="" />
          <el-option v-for="sys in systems" :key="sys.sysCode" :label="sys.sysName + ' (' + sys.sysCode + ')'" :value="sys.sysCode" />
        </el-select>
        <el-input v-model="pathFilter" placeholder="筛选 URL 后缀" clearable size="small" @input="onFilterChange">
          <font-awesome-icon slot="prefix" icon="magnifying-glass" class="search-icon" />
        </el-input>
        <el-input v-model="descFilter" placeholder="筛选描述" clearable size="small" @input="onFilterChange">
          <font-awesome-icon slot="prefix" icon="magnifying-glass" class="search-icon" />
        </el-input>
        <el-button size="small" @click="resetFilters">重置</el-button>
      </div>

      <div class="table-wrap">
        <el-table
          v-loading="loading"
          :data="pageRows"
          row-key="id"
          empty-text="没有匹配的接口配置"
          size="small"
        >
          <el-table-column label="编码 / 描述" min-width="180">
            <template #default="{ row }">
              <div class="cell-name">{{ row.sourceCode }}</div>
              <div class="cell-sub">{{ row.sourceName }}</div>
            </template>
          </el-table-column>
          <el-table-column label="方式" width="80">
            <template #default="{ row }">
              <el-tag size="mini" :class="'method-' + row.method.toLowerCase()">{{ row.method }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="所属系统" width="160">
            <template #default="{ row }">{{ systemName(row.sysCode) }}</template>
          </el-table-column>
          <el-table-column label="URL 后缀" min-width="200">
            <template #default="{ row }">
              <span class="cell-mono">{{ row.path }}</span>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="80" align="center">
            <template #default="{ row }">
              <el-tag :type="row.status === 'ENABLED' ? 'success' : 'info'" size="mini">
                {{ row.status === 'ENABLED' ? '启用' : '停用' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="140" align="right">
            <template #default="{ row }">
              <el-button type="text" size="small" @click="handleView(row)">
                <font-awesome-icon icon="eye" />
              </el-button>
              <el-button type="text" size="small" @click="handleEdit(row)">
                <font-awesome-icon icon="pen" />
              </el-button>
              <el-dropdown trigger="click" @command="onRowCommand($event, row)">
                <el-button type="text" size="small">
                  <font-awesome-icon icon="ellipsis-vertical" />
                </el-button>
                <el-dropdown-menu slot="dropdown">
                  <el-dropdown-item command="copy">
                    <font-awesome-icon icon="copy" class="menu-icon" /> 复制
                  </el-dropdown-item>
                  <el-dropdown-item command="curl">
                    <font-awesome-icon icon="terminal" class="menu-icon" /> 导出 cURL
                  </el-dropdown-item>
                  <el-dropdown-item command="delete" class="cmd-danger">
                    <font-awesome-icon icon="trash" class="menu-icon" /> 删除
                  </el-dropdown-item>
                </el-dropdown-menu>
              </el-dropdown>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <div class="pager">
        <el-pagination
          background
          layout="total, prev, pager, next"
          :total="filteredSources.length"
          :page-size="pageSize"
          :current-page="page + 1"
          @current-change="onPageChange"
        />
      </div>
    </template>

    <!-- ── Editor View ── -->
    <template v-else>
      <div class="editor-view">
        <el-row type="flex" justify="space-between" align="middle" class="editor-header">
          <el-col :span="12" class="header-left">
            <el-button type="text" @click="closeEditor">
              <font-awesome-icon icon="arrow-left" /> 返回列表
            </el-button>
            <h3>{{ isNew ? '新增接口' : (editorMode === 'view' ? '查看接口' : '编辑接口') }}</h3>
          </el-col>
          <el-col :span="12" class="header-right">
            <el-button size="small" @click="showCurlDialog = true">
              <font-awesome-icon icon="terminal" /> cURL
            </el-button>
            <el-button size="small" type="success" plain @click="openTestDialog">
              <font-awesome-icon icon="play" /> 测试
            </el-button>
            <template v-if="editorMode !== 'view'">
              <el-button size="small" @click="closeEditor">取消</el-button>
              <el-button size="small" type="primary" :loading="saving" @click="handleSave">
                <font-awesome-icon v-if="!saving" icon="floppy-disk" /> 保存
              </el-button>
            </template>
          </el-col>
        </el-row>

        <div class="editor-body" :class="{ 'is-disabled': editorMode === 'view' }">
          <el-form label-position="top" size="small">
            <!-- Basic info -->
            <el-row :gutter="16">
              <el-col :span="12">
                <el-form-item label="接口编码" required>
                  <el-input v-model="editing.sourceCode" :disabled="!isNew" placeholder="唯一编码" />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="接口名称" required>
                  <el-input v-model="editing.sourceName" placeholder="显示名称" />
                </el-form-item>
              </el-col>
            </el-row>
            <el-form-item label="状态">
              <el-select v-model="editing.status">
                <el-option label="启用" value="ENABLED" />
                <el-option label="停用" value="DISABLED" />
              </el-select>
            </el-form-item>

            <!-- ── Section: 请求配置 ── -->
            <el-collapse v-model="activeSections" class="editor-collapse">
              <el-collapse-item name="request">
                <template slot="title">
                  <span class="section-title">请求配置</span>
                  <el-tag size="mini" type="info" class="section-summary">{{ editing.method }} {{ editing.path || '未配置 URL' }}</el-tag>
                </template>

                <!-- Address bar -->
                <el-row :gutter="8" class="address-bar">
                  <el-col :span="3">
                    <el-select v-model="editing.method" class="addr-method">
                      <el-option v-for="m in httpMethods" :key="m" :label="m" :value="m" />
                    </el-select>
                  </el-col>
                  <el-col :span="6">
                    <el-select v-model="editing.sysCode" class="addr-sys" placeholder="选择系统" clearable>
                      <el-option v-for="s in systemOptions" :key="s.code" :label="s.name + ' (' + s.code + ')'" :value="s.code" />
                    </el-select>
                  </el-col>
                  <el-col :span="15">
                    <el-input v-model="editing.path" class="addr-path" placeholder="https://api.example.com/v1/resource" />
                  </el-col>
                </el-row>
                <p v-if="selectedEndpoints.length > 0" class="endpoint-hint">
                  已配置环境端点:
                  <span v-for="ep in selectedEndpoints" :key="ep.id" class="endpoint-item">
                    {{ ep.envCode }}: {{ ep.baseUrl }}
                  </span>
                </p>

                <!-- Timeout grid -->
                <el-row :gutter="16" class="timeout-grid">
                  <el-col v-for="tf in timeoutFields" :key="tf.key" :span="6">
                    <el-form-item :label="tf.label + '超时（秒）'" size="small">
                      <el-input-number
                        :value="editing.timeoutConfig[tf.key]"
                        :min="1"
                        :max="60"
                        :step="1"
                        controls-position="right"
                        @change="onTimeoutChange(tf.key, $event)"
                      />
                    </el-form-item>
                  </el-col>
                </el-row>

              <!-- Request tabs -->
              <el-tabs v-model="requestTab" class="request-tabs">
                <!-- Params -->
                <el-tab-pane name="params">
                  <span slot="label">
                    <font-awesome-icon icon="globe" /> Params
                    <span v-if="paramCount > 0" class="tab-badge">{{ paramCount }}</span>
                  </span>
                  <field-mapper
                    label="Query Params"
                    description="URL 问号后面的参数, 如 ?id=1&name=test"
                    :value="rmQuery"
                    placeholder="Param Key"
                    :descriptions="rmQueryDesc"
                    @change="onRmSectionChange('query', $event)"
                    @update:descriptions="onRmSectionChange('_queryDesc', $event)"
                  />
                </el-tab-pane>

                <!-- Auth -->
                <el-tab-pane name="auth">
                  <span slot="label">
                    <font-awesome-icon icon="key" /> Auth
                    <span v-if="authType !== 'none'" class="tab-dot tab-dot--green" />
                  </span>
                  <div class="auth-section">
                    <div class="auth-type-row">
                      <span class="auth-type-label">认证类型</span>
                      <el-select :value="authType" size="small" class="auth-type-select" @input="onAuthTypeChange">
                        <el-option label="No Auth" value="none" />
                        <el-option label="Bearer Token" value="bearer" />
                        <el-option label="Basic Auth" value="basic" />
                        <el-option label="API Key" value="apikey" />
                      </el-select>
                    </div>
                    <div v-if="authType === 'bearer'" class="auth-form">
                      <span class="auth-field-label">Token</span>
                      <el-input :value="authConfig.token || ''" placeholder="Bearer Token 或变量引用" class="mono-input" @input="updateAuth({ ...authConfig, token: $event })" />
                    </div>
                    <div v-if="authType === 'basic'" class="auth-form">
                      <el-row :gutter="16">
                        <el-col :span="12">
                          <span class="auth-field-label">Username</span>
                          <el-input :value="authConfig.username || ''" placeholder="用户名" @input="updateAuth({ ...authConfig, username: $event })" />
                        </el-col>
                        <el-col :span="12">
                          <span class="auth-field-label">Password</span>
                          <el-input :value="authConfig.password || ''" placeholder="密码" class="mono-input" @input="updateAuth({ ...authConfig, password: $event })" />
                        </el-col>
                      </el-row>
                    </div>
                    <div v-if="authType === 'apikey'" class="auth-form">
                      <el-row :gutter="16">
                        <el-col :span="8">
                          <span class="auth-field-label">Key</span>
                          <el-input :value="authConfig.key || ''" placeholder="如 X-API-Key" class="mono-input" @input="updateAuth({ ...authConfig, key: $event })" />
                        </el-col>
                        <el-col :span="8">
                          <span class="auth-field-label">Value</span>
                          <el-input :value="authConfig.value || ''" placeholder="API Key 或 ${...}" class="mono-input" @input="updateAuth({ ...authConfig, value: $event })" />
                        </el-col>
                        <el-col :span="8">
                          <span class="auth-field-label">添加到</span>
                          <el-select :value="authConfig.addTo || 'header'" @input="updateAuth({ ...authConfig, addTo: $event })">
                            <el-option label="Header" value="header" />
                            <el-option label="Query" value="query" />
                          </el-select>
                        </el-col>
                      </el-row>
                    </div>
                  </div>
                </el-tab-pane>

                <!-- Headers -->
                <el-tab-pane name="headers">
                  <span slot="label">
                    <font-awesome-icon icon="shield-halved" /> Headers
                    <span v-if="headerCount > 0" class="tab-badge">{{ headerCount }}</span>
                  </span>
                  <header-field-mapper
                    label="Request Headers"
                    description="HTTP 请求头"
                    :value="rmHeaders"
                    placeholder="Header Name"
                    :descriptions="rmHeadersDesc"
                    @change="onRmSectionChange('headers', $event)"
                    @update:descriptions="onRmSectionChange('_headersDesc', $event)"
                  />
                </el-tab-pane>

                <!-- Body -->
                <el-tab-pane name="body">
                  <span slot="label">
                    <font-awesome-icon icon="code" /> Body
                    <span v-if="hasBody" class="tab-dot tab-dot--blue" />
                  </span>
                  <div class="body-section">
                    <el-radio-group :value="bodyType" size="small" @input="onBodyTypeChange">
                      <el-radio-button label="none">none</el-radio-button>
                      <el-radio-button label="form-data">form-data</el-radio-button>
                      <el-radio-button label="x-www-form-urlencoded">x-www-form-urlencoded</el-radio-button>
                      <el-radio-button label="raw-json">raw JSON</el-radio-button>
                      <el-radio-button label="raw-text">raw Text</el-radio-button>
                      <el-radio-button label="raw-xml">raw XML</el-radio-button>
                    </el-radio-group>

                    <div class="body-content">
                      <template v-if="bodyType === 'none'">
                        <div class="body-empty">该请求没有请求体</div>
                      </template>
                      <template v-else-if="bodyType === 'form-data'">
                        <field-mapper
                          label="Form Data"
                          description="multipart/form-data 表单字段"
                          :value="rmFormData"
                          placeholder="字段名"
                          @change="onRmSectionChange('formData', $event)"
                        />
                      </template>
                      <template v-else-if="bodyType === 'x-www-form-urlencoded'">
                        <field-mapper
                          label="URL Encoded"
                          description="application/x-www-form-urlencoded 表单"
                          :value="rmUrlEncoded"
                          placeholder="字段名"
                          :descriptions="rmUrlEncodedDesc"
                          @change="onRmSectionChange('urlEncodedData', $event)"
                          @update:descriptions="onRmSectionChange('_urlEncodedDesc', $event)"
                        />
                      </template>
                      <template v-else-if="bodyType === 'raw-json' || bodyType === 'raw-xml'">
                        <body-tree-editor
                          :format="bodyType === 'raw-xml' ? 'xml' : 'json'"
                          :step="bodyTreeStep"
                          @change="onBodyTreeChange"
                        />
                      </template>
                      <template v-else-if="bodyType === 'raw-text'">
                        <el-input
                          :value="rmRawBody"
                          type="textarea"
                          :rows="8"
                          placeholder="输入纯文本请求体"
                          @input="onRmSectionChange('rawBody', $event)"
                        />
                      </template>
                    </div>
                  </div>
                </el-tab-pane>
              </el-tabs>
              </el-collapse-item>

              <!-- ── Section: 响应报文定义 ── -->
              <el-collapse-item name="response">
                <template slot="title">
                  <span class="section-title">响应报文定义</span>
                </template>
              <el-tabs v-model="responseTab" class="response-tabs">
                <!-- Body -->
                <el-tab-pane name="body">
                  <span slot="label">
                    <font-awesome-icon icon="code" /> Body
                    <span v-if="responseBodyFieldCount > 0" class="tab-badge">{{ responseBodyFieldCount }}</span>
                  </span>
                  <div class="resp-toolbar">
                    <el-radio-group v-model="responseBodyView" size="small">
                      <el-radio-button label="tree">
                        <font-awesome-icon icon="folder-tree" /> 树状
                      </el-radio-button>
                      <el-radio-button label="preview">
                        <font-awesome-icon icon="eye" /> 预览
                      </el-radio-button>
                    </el-radio-group>
                    <el-select v-model="responseContentType" size="small" class="resp-ct-select" @change="onResponseContentTypeChange">
                      <el-option label="JSON" value="JSON">
                        <span><font-awesome-icon icon="file-code" /> JSON</span>
                      </el-option>
                      <el-option label="XML" value="XML">
                        <span><font-awesome-icon icon="file-code" /> XML</span>
                      </el-option>
                      <el-option label="Text" value="TEXT">
                        <span><font-awesome-icon icon="file-lines" /> Text</span>
                      </el-option>
                    </el-select>
                    <el-button size="small" class="resp-import-btn" @click="openImportDialog">
                      <font-awesome-icon :icon="importIconForFormat" /> 贴入报文样例
                    </el-button>
                  </div>

                  <!-- Tree view -->
                  <div v-if="responseBodyView === 'tree'" class="resp-tree">
                    <div class="resp-tree-head">
                      <div>Key</div>
                      <div>Type</div>
                      <div>示例值</div>
                      <div>Description</div>
                    </div>
                    <div v-if="responseSchema.length === 0" class="resp-tree-empty">
                      暂无报文结构，点击"贴入报文样例"导入
                    </div>
                    <div v-else class="resp-tree-body">
                      <response-schema-node
                        v-for="(field, idx) in responseSchema"
                        :key="idx"
                        :field="field"
                        :flat-index="getResponseFlatIndex(idx)"
                        :depth="0"
                        :on-update-field="updateResponseFieldProp"
                      />
                    </div>
                  </div>

                  <!-- Preview view -->
                  <div v-else class="resp-preview">
                    <span class="resp-preview-hint">预览模式 · 基于树状结构生成的 {{ responseContentType }} 样例</span>
                    <json-code-mirror
                      v-if="responseContentType === 'JSON'"
                      :value="responsePreviewText"
                      :read-only="true"
                      height="300px"
                    />
                    <pre v-else class="resp-preview-text">{{ responsePreviewText || '暂无样例' }}</pre>
                  </div>
                </el-tab-pane>

                <!-- Headers -->
                <el-tab-pane name="respHeaders">
                  <span slot="label">
                    <font-awesome-icon icon="file-lines" /> Headers
                    <span v-if="responseHeadersSchema.length > 0" class="tab-badge">{{ responseHeadersSchema.length }}</span>
                  </span>
                  <div class="resp-headers-toolbar">
                    <el-button size="small" @click="openImportHeadersDialog">
                      <font-awesome-icon icon="file-lines" /> 贴入 Headers
                    </el-button>
                    <el-button type="text" @click="addResponseHeader">
                      <font-awesome-icon icon="plus" />
                    </el-button>
                  </div>
                  <el-table :data="responseHeadersSchema" size="small" empty-text="暂无响应头定义" border>
                    <el-table-column label="KEY" min-width="150">
                      <template slot-scope="{ row, $index }">
                        <el-input :value="row.name" size="small" class="mono-input" placeholder="Header-Name" @input="updateResponseHeader($index, 'name', $event)" />
                      </template>
                    </el-table-column>
                    <el-table-column label="TYPE" width="110">
                      <template slot-scope="{ row, $index }">
                        <el-select :value="row.type" size="small" @input="updateResponseHeader($index, 'type', $event)">
                          <el-option label="string" value="string" />
                          <el-option label="number" value="number" />
                          <el-option label="boolean" value="boolean" />
                        </el-select>
                      </template>
                    </el-table-column>
                    <el-table-column label="VALUE" min-width="150">
                      <template slot-scope="{ row, $index }">
                        <el-input :value="row.defaultValue || ''" size="small" class="mono-input" placeholder="示例值" @input="updateResponseHeader($index, 'defaultValue', $event)" />
                      </template>
                    </el-table-column>
                    <el-table-column label="DESCRIPTION" min-width="150">
                      <template slot-scope="{ row, $index }">
                        <el-input :value="row.label || ''" size="small" placeholder="说明" @input="updateResponseHeader($index, 'label', $event)" />
                      </template>
                    </el-table-column>
                    <el-table-column label="" width="50" align="center">
                      <template slot-scope="{ $index }">
                        <el-button type="text" class="del-btn" @click="removeResponseHeader($index)">
                          <font-awesome-icon icon="trash" />
                        </el-button>
                      </template>
                    </el-table-column>
                  </el-table>
                </el-tab-pane>

                <!-- Cookies -->
                <el-tab-pane name="respCookies">
                  <span slot="label">
                    <font-awesome-icon icon="cookie-bite" /> Cookies
                    <span v-if="responseCookiesSchema.length > 0" class="tab-badge">{{ responseCookiesSchema.length }}</span>
                  </span>
                  <div class="resp-cookies-toolbar">
                    <el-button type="text" @click="addResponseCookie">
                      <font-awesome-icon icon="plus" />
                    </el-button>
                  </div>
                  <div class="resp-cookies-table">
                    <div class="resp-cookies-head">
                      <div>Name</div>
                      <div>Type</div>
                      <div>Value</div>
                      <div>Domain</div>
                      <div>Path</div>
                      <div>Expires</div>
                      <div class="resp-center">HttpOnly</div>
                      <div class="resp-center">Secure</div>
                      <div class="resp-center">DEL</div>
                    </div>
                    <div v-if="responseCookiesSchema.length === 0" class="resp-cookies-empty">暂无 Cookie 定义</div>
                    <div v-for="(c, i) in responseCookiesSchema" :key="i" class="resp-cookies-row">
                      <el-input :value="c.name" size="small" class="mono-input" placeholder="cookie_name" @input="updateResponseCookie(i, 'name', $event)" />
                      <el-select :value="c.type" size="small" @input="updateResponseCookie(i, 'type', $event)">
                        <el-option label="string" value="string" />
                        <el-option label="number" value="number" />
                      </el-select>
                      <el-input :value="c.defaultValue || ''" size="small" class="mono-input" placeholder="示例值" @input="updateResponseCookie(i, 'defaultValue', $event)" />
                      <el-input :value="cookieExtra(i, 'domain')" size="small" placeholder="/" @input="updateCookieExtra(i, 'domain', $event)" />
                      <el-input :value="cookieExtra(i, 'path')" size="small" placeholder="/" @input="updateCookieExtra(i, 'path', $event)" />
                      <el-input :value="cookieExtra(i, 'expires')" size="small" placeholder="Session" @input="updateCookieExtra(i, 'expires', $event)" />
                      <div class="resp-center">
                        <el-checkbox :value="cookieFlag(i, 'httpOnly')" @change="toggleCookieFlag(i, 'httpOnly', $event)" />
                      </div>
                      <div class="resp-center">
                        <el-checkbox :value="cookieFlag(i, 'secure')" @change="toggleCookieFlag(i, 'secure', $event)" />
                      </div>
                      <div class="resp-center">
                        <el-button type="text" class="del-btn" @click="removeResponseCookie(i)">
                          <font-awesome-icon icon="trash" />
                        </el-button>
                      </div>
                    </div>
                  </div>
                </el-tab-pane>
              </el-tabs>
              </el-collapse-item>

              <!-- ── Section: 业务规则 ── -->
              <el-collapse-item name="rules">
                <template slot="title">
                  <span class="section-title">业务成功 / 失败判定</span>
                </template>

                <!-- Success rules (AND) -->
                <el-card shadow="never" class="inner-card">
                  <div slot="header" class="card-header-row">
                    <span>
                      <font-awesome-icon icon="check-circle" class="rules-icon rules-icon--success" />
                      业务成功条件（全部满足 · AND）
                    </span>
                    <el-button type="text" @click="addSuccessRule">
                      <font-awesome-icon icon="plus" />
                    </el-button>
                  </div>
                  <div v-if="successRules.length === 0" class="rules-empty">无规则，默认按状态码判定</div>
                  <el-row v-for="(rule, i) in successRules" :key="'s'+i" :gutter="8" class="rule-row" type="flex" align="middle">
                    <el-col :span="8">
                      <el-input :value="rule.path" size="small" class="mono-input" placeholder="$.code 或 ${RES_BODY(success)}" @input="updateSuccessRule(i, 'path', $event)" />
                    </el-col>
                    <el-col :span="5">
                      <el-select :value="rule.op" size="small" class="rule-op" @input="updateSuccessRule(i, 'op', $event)">
                        <el-option v-for="op in conditionOps" :key="op" :label="op" :value="op" />
                      </el-select>
                    </el-col>
                    <el-col :span="8">
                      <el-input :value="ruleValueStr(rule)" size="small" placeholder="期望值" @input="updateSuccessRule(i, 'value', $event)" />
                    </el-col>
                    <el-col :span="3">
                      <el-button type="text" class="del-btn" @click="removeSuccessRule(i)">
                        <font-awesome-icon icon="trash" />
                      </el-button>
                    </el-col>
                  </el-row>

                  <el-divider />

                  <!-- Status codes -->
                  <el-form-item label="成功状态码">
                    <el-input v-model="successStatusCodes" size="small" placeholder="200, 201" />
                  </el-form-item>
                </el-card>

                <!-- Failure rules (OR) -->
                <el-card shadow="never" class="inner-card">
                  <div slot="header" class="card-header-row">
                    <span>
                      <font-awesome-icon icon="times-circle" class="rules-icon rules-icon--failure" />
                      业务失败条件（任一满足 · OR）
                    </span>
                    <el-button type="text" @click="addFailureRule">
                      <font-awesome-icon icon="plus" />
                    </el-button>
                  </div>
                  <div v-if="failureRules.length === 0" class="rules-empty">无规则</div>
                  <el-row v-for="(rule, i) in failureRules" :key="'f'+i" :gutter="8" class="rule-row" type="flex" align="middle">
                    <el-col :span="8">
                      <el-input :value="rule.path" size="small" class="mono-input" placeholder="$.code" @input="updateFailureRule(i, 'path', $event)" />
                    </el-col>
                    <el-col :span="5">
                      <el-select :value="rule.op" size="small" class="rule-op" @input="updateFailureRule(i, 'op', $event)">
                        <el-option v-for="op in conditionOps" :key="op" :label="op" :value="op" />
                      </el-select>
                    </el-col>
                    <el-col :span="8">
                      <el-input :value="ruleValueStr(rule)" size="small" placeholder="期望值" @input="updateFailureRule(i, 'value', $event)" />
                    </el-col>
                    <el-col :span="3">
                      <el-button type="text" class="del-btn" @click="removeFailureRule(i)">
                        <font-awesome-icon icon="trash" />
                      </el-button>
                    </el-col>
                  </el-row>
                </el-card>
              </el-collapse-item>

              <!-- ── Section: 错误映射 ── -->
              <el-collapse-item name="errorMapping">
                <template slot="title">
                  <span class="section-title">错误映射与重试策略</span>
                </template>

                <!-- Network error mapping -->
                <el-card shadow="never" class="inner-card">
                  <div slot="header">
                    <font-awesome-icon icon="exclamation-triangle" class="em-icon" />
                    网络错误映射
                  </div>
                  <el-form-item label="消息模板">
                    <el-input :value="errorMapping.messageTemplate || ''" placeholder="如: 调用 {sysCode} 失败: {message}" @input="updateErrorMapping('messageTemplate', $event)" />
                  </el-form-item>
                  <el-form-item label="字段映射">
                    <el-input :value="errorMappingFieldsJson" type="textarea" :rows="2" @input="onErrorMappingFieldsInput" />
                  </el-form-item>
                  <el-form-item label="兜底消息">
                    <el-input :value="errorMapping.fallbackMessage || ''" placeholder="未知错误" @input="updateErrorMapping('fallbackMessage', $event)" />
                  </el-form-item>
                  <el-form-item label="暴露原始响应">
                    <el-switch :value="errorMapping.exposeRawResponse" @change="updateErrorMapping('exposeRawResponse', $event)" />
                  </el-form-item>
                </el-card>

                <!-- Business error mapping -->
                <el-card shadow="never" class="inner-card">
                  <div slot="header">
                    <font-awesome-icon icon="exclamation-circle" class="em-icon" />
                    业务错误映射
                  </div>
                  <el-form-item label="消息模板">
                    <el-input :value="businessErrorMapping.messageTemplate || ''" placeholder="如: 业务错误 [{code}]: {message}" @input="updateBusinessErrorMapping('messageTemplate', $event)" />
                  </el-form-item>
                  <el-form-item label="字段映射">
                    <el-input :value="businessErrorMappingFieldsJson" type="textarea" :rows="2" @input="onBusinessErrorMappingFieldsInput" />
                  </el-form-item>
                  <el-form-item label="兜底消息">
                    <el-input :value="businessErrorMapping.fallbackMessage || ''" placeholder="业务处理失败" @input="updateBusinessErrorMapping('fallbackMessage', $event)" />
                  </el-form-item>
                  <el-form-item label="暴露原始响应">
                    <el-switch :value="businessErrorMapping.exposeRawResponse" @change="updateBusinessErrorMapping('exposeRawResponse', $event)" />
                  </el-form-item>
                </el-card>

                <!-- Retry policy -->
                <el-card shadow="never" class="inner-card">
                  <div slot="header">
                    <font-awesome-icon icon="redo" class="em-icon" />
                    重试策略
                  </div>
                  <el-form-item label="启用重试">
                    <el-switch v-model="retryEnabled" />
                  </el-form-item>
                  <template v-if="retryEnabled">
                    <el-row :gutter="16">
                      <el-col :span="12">
                        <el-form-item label="最大重试次数">
                          <el-input-number v-model="retryPolicy.maxAttempts" :min="1" :max="10" />
                        </el-form-item>
                      </el-col>
                      <el-col :span="12">
                        <el-form-item label="重试间隔 (ms)">
                          <el-input-number v-model="retryPolicy.intervalMs" :min="100" :max="60000" :step="500" />
                        </el-form-item>
                      </el-col>
                    </el-row>
                    <el-form-item label="重试条件">
                      <el-checkbox-group v-model="retryPolicy.retryOn">
                        <el-checkbox label="NETWORK_TIMEOUT">网络超时</el-checkbox>
                        <el-checkbox label="CONNECTION_RESET">连接重置</el-checkbox>
                        <el-checkbox label="HTTP_5XX">HTTP 5xx</el-checkbox>
                        <el-checkbox label="RATE_LIMIT">限流</el-checkbox>
                      </el-checkbox-group>
                    </el-form-item>
                  </template>
                </el-card>
              </el-collapse-item>

              <!-- ── Section: Output Extraction ── -->
              <el-collapse-item name="output">
                <template slot="title">
                  <span class="section-title">输出映射</span>
                </template>
                <http-output-extraction-editor
                  :step="outputStepProxy"
                  :disabled="editorMode === 'view'"
                  @change="onOutputExtractionChange"
                />
              </el-collapse-item>
            </el-collapse>
          </el-form>
        </div>
      </div>
    </template>

    <!-- ── Import Dialog ── -->
    <el-dialog title="贴入报文样例" :visible.sync="importDialogVisible" width="700px" append-to-body>
      <div class="import-toolbar">
        <el-radio-group v-model="importFormat" size="small">
          <el-radio-button label="json">JSON</el-radio-button>
          <el-radio-button label="xml">XML</el-radio-button>
          <el-radio-button label="text">Text</el-radio-button>
          <el-radio-button label="headers">Headers</el-radio-button>
        </el-radio-group>
      </div>
      <div class="import-editor">
        <json-code-mirror
          v-if="importFormat === 'json'"
          :value="importInput"
          height="300px"
          placeholder="在此贴入 JSON 报文..."
          @change="importInput = $event"
        />
        <textarea
          v-else
          v-model="importInput"
          class="import-textarea"
          :placeholder="importPlaceholder"
        />
      </div>
      <span slot="footer">
        <el-button @click="importDialogVisible = false">取消</el-button>
        <el-button type="primary" :disabled="!importInput.trim()" @click="handleImport">解析并导入</el-button>
      </span>
    </el-dialog>

    <!-- ── Test Dialog ── -->
    <el-dialog title="接口测试" :visible.sync="testDialogVisible" width="800px" append-to-body>
      <div class="test-env-row">
        <el-select v-model="testEnvCode" placeholder="选择环境" size="small">
          <el-option v-for="env in environments" :key="env.envCode" :label="env.envName" :value="env.envCode" />
        </el-select>
        <el-button type="primary" size="small" :loading="testing" :disabled="!testEnvCode" @click="runTest">
          <font-awesome-icon icon="play" /> 执行测试
        </el-button>
      </div>

      <div v-if="testResult" class="test-result-area">
        <el-tabs v-model="testTab">
          <!-- Response tab -->
          <el-tab-pane name="resp">
            <span slot="label">
              响应
              <el-tag :type="testResult.success ? 'success' : 'danger'" size="mini" class="ml-1">
                {{ testResult.success ? '成功' : '失败' }}
              </el-tag>
            </span>

            <!-- Status + metrics -->
            <div class="test-metrics">
              <span v-if="testResult.response" class="metric-item">
                <span class="metric-label">Status:</span>
                <el-tag :type="statusTagType(testResult.response.statusCode)" size="mini">
                  {{ testResult.response.statusCode }}
                </el-tag>
              </span>
              <span v-if="testResult.response && testResult.response.elapsedMs != null" class="metric-item">
                <span class="metric-label">耗时:</span>
                <span class="metric-value">{{ testResult.response.elapsedMs }}ms</span>
              </span>
            </div>

            <!-- Business result -->
            <div v-if="testResult.businessResult" class="test-block">
              <div class="test-block-title">
                <font-awesome-icon :icon="testResult.businessResult.isSuccess ? 'check-circle' : 'times-circle'" :class="testResult.businessResult.isSuccess ? 'text-success' : 'text-danger'" />
                业务判定: {{ testResult.businessResult.isSuccess ? '成功' : '失败' }}
              </div>
              <p class="test-block-text">{{ testResult.businessResult.reason }}</p>
            </div>

            <!-- Response body -->
            <div v-if="testResult.response" class="test-block">
              <div class="test-block-title">Response Body</div>
              <pre class="test-pre">{{ formatJson(testResult.response.body) }}</pre>
            </div>

            <!-- Response headers -->
            <div v-if="testResult.response" class="test-block">
              <div class="test-block-title">Response Headers</div>
              <pre class="test-pre">{{ formatJson(testResult.response.headers) }}</pre>
            </div>

            <!-- Cookies -->
            <div v-if="testResult.response && testResult.response.cookies && testResult.response.cookies.length > 0" class="test-block">
              <div class="test-block-title">Cookies</div>
              <el-table :data="testResult.response.cookies" size="mini" border>
                <el-table-column prop="name" label="Name" min-width="120">
                  <template slot-scope="{ row }">
                    <span class="mono-cell">{{ row.name }}</span>
                  </template>
                </el-table-column>
                <el-table-column prop="value" label="Value" min-width="150" show-overflow-tooltip>
                  <template slot-scope="{ row }">
                    <span class="mono-cell">{{ row.value }}</span>
                  </template>
                </el-table-column>
                <el-table-column prop="domain" label="Domain" width="110">
                  <template slot-scope="{ row }">{{ row.domain || '-' }}</template>
                </el-table-column>
                <el-table-column prop="path" label="Path" width="70">
                  <template slot-scope="{ row }">{{ row.path || '/' }}</template>
                </el-table-column>
                <el-table-column prop="expires" label="Expires" width="110">
                  <template slot-scope="{ row }">{{ row.expires || '-' }}</template>
                </el-table-column>
                <el-table-column label="HttpOnly" width="75" align="center">
                  <template slot-scope="{ row }">
                    <el-tag v-if="row.httpOnly" size="mini" type="info">Yes</el-tag>
                    <span v-else class="text-muted-sm">-</span>
                  </template>
                </el-table-column>
                <el-table-column label="Secure" width="70" align="center">
                  <template slot-scope="{ row }">
                    <el-tag v-if="row.secure" size="mini" type="info">Yes</el-tag>
                    <span v-else class="text-muted-sm">-</span>
                  </template>
                </el-table-column>
              </el-table>
            </div>

            <!-- Extracted outputs -->
            <div v-if="testResult.extractedOutputs && Object.keys(testResult.extractedOutputs).length > 0" class="test-block">
              <div class="test-block-title">提取的输出</div>
              <pre class="test-pre">{{ formatJson(testResult.extractedOutputs) }}</pre>
            </div>

            <!-- Retry info -->
            <div v-if="testResult.retryInfo && testResult.retryInfo.attempts > 0" class="test-block">
              <div class="test-block-title">重试信息</div>
              <p>重试次数: {{ testResult.retryInfo.attempts }}</p>
              <p v-if="testResult.retryInfo.lastError">最后错误: {{ testResult.retryInfo.lastError }}</p>
            </div>

            <!-- Error -->
            <div v-if="testResult.error" class="test-block test-block--error">
              <div class="test-block-title">
                <font-awesome-icon icon="exclamation-triangle" /> 错误详情
              </div>
              <p class="test-error-type">{{ testResult.error.type }}</p>
              <p>{{ testResult.error.message }}</p>
              <pre v-if="testResult.error.detail" class="test-pre">{{ testResult.error.detail }}</pre>
            </div>
          </el-tab-pane>

          <!-- Request tab -->
          <el-tab-pane name="req" label="请求">
            <div v-if="testResult" class="test-request-area">
              <!-- Curl command -->
              <div class="test-block">
                <div class="test-block-title">
                  cURL Command
                  <el-button type="text" size="small" class="copy-btn" @click="copyCurlCommand">
                    <font-awesome-icon icon="copy" /> 复制
                  </el-button>
                </div>
                <pre class="test-pre test-curl">{{ testCurlCommand }}</pre>
              </div>
              <!-- Request headers + query -->
              <div class="test-grid-2col">
                <div class="test-block">
                  <div class="test-block-title">Request Headers</div>
                  <pre class="test-pre">{{ formatJson(testResult.request.headers) }}</pre>
                </div>
                <div v-if="testResult.request.query && Object.keys(testResult.request.query).length > 0" class="test-block">
                  <div class="test-block-title">Query Parameters</div>
                  <pre class="test-pre">{{ formatJson(testResult.request.query) }}</pre>
                </div>
              </div>
              <!-- Request body -->
              <div v-if="testResult.request.body != null" class="test-block">
                <div class="test-block-title">
                  Request Body
                  <span v-if="testResult.request.bodyType" class="test-body-type">{{ testResult.request.bodyType }}</span>
                </div>
                <pre class="test-pre">{{ formatJson(testResult.request.body) }}</pre>
              </div>
            </div>
          </el-tab-pane>
        </el-tabs>
      </div>

      <span slot="footer">
        <el-button @click="testDialogVisible = false">关闭</el-button>
      </span>
    </el-dialog>

    <!-- ── Curl Export Dialog ── -->
    <el-dialog title="导出 cURL 命令" :visible.sync="showCurlDialog" width="640px" append-to-body>
      <pre class="curl-export-pre">{{ curlCommandText }}</pre>
      <span slot="footer">
        <el-button @click="showCurlDialog = false">关闭</el-button>
        <el-button type="primary" @click="copyText(curlCommandText)">
          <font-awesome-icon icon="copy" /> 复制到剪贴板
        </el-button>
      </span>
    </el-dialog>

    <!-- ── Delete Dialog ── -->
    <el-dialog title="确认删除" :visible.sync="deleteDialogVisible" width="440px">
      <p>确定删除接口配置 "{{ deleteTarget }}" 吗？此操作不可撤销。</p>
      <span slot="footer">
        <el-button @click="deleteDialogVisible = false">取消</el-button>
        <el-button type="danger" @click="confirmDelete">确认删除</el-button>
      </span>
    </el-dialog>
  </div>
</template>

<script lang="ts">
import Vue from 'vue'

import {
  createHttpSource,
  deleteHttpSource,
  listEnvironments,
  listHttpSources,
  listServiceEndpoints,
  listSystems,
  testHttpSource,
  updateHttpSource,
} from '@/datagen/common/lib/api'
import {
  createDefaultHttpSource,
  createConditionRule,
  HTTP_METHODS,
} from '@/datagen/common/lib/defaults'
import type {
  ConditionOperator,
  ConditionRule,
  EnvironmentResponse,
  ErrorMapping,
  HttpMethod,
  HttpSourceConfig,
  HttpSourceResponse,
  HttpSourceTestResult,
  HttpStepDefinition,
  HttpTimeoutConfig,
  InputFieldDefinition,
  RetryPolicy,
  ResponseHandling,
  ServiceEndpointResponse,
  SysResponse,
} from '@/datagen/common/lib/types'
import {
  countFields,
  getFlatIndex,
  jsonToFields,
  parseJsonWithComments,
  updateFieldPropAtPath,
} from '@/datagen/common/lib/schema-utils'
import {
  treeToSample,
  jsonToXml,
  xmlToTree,
} from '@/datagen/common/lib/body-tree-utils'

import BodyTreeEditor from '../components/body-tree-editor.vue'
import FieldMapper from '../components/field-mapper.vue'
import HeaderFieldMapper from '../components/header-field-mapper.vue'
import HttpOutputExtractionEditor from '../components/http-output-extraction-editor.vue'
import JsonCodeMirror from '../components/json-code-mirror.vue'
import ResponseSchemaNode from '../components/response-schema-node.vue'

/* ── 类型 ── */

type AuthType = 'none' | 'bearer' | 'basic' | 'apikey'
interface AuthConfig {
  type: AuthType
  token?: string
  username?: string
  password?: string
  key?: string
  value?: string
  addTo?: 'header' | 'query'
}

type BodyType = 'none' | 'form-data' | 'x-www-form-urlencoded' | 'raw-json' | 'raw-text' | 'raw-xml'

type TimeoutKey = keyof HttpTimeoutConfig

const TIMEOUT_FIELDS: Array<{ key: TimeoutKey; label: string }> = [
  { key: 'connectTimeoutSeconds', label: '连接' },
  { key: 'readTimeoutSeconds', label: '读取' },
  { key: 'writeTimeoutSeconds', label: '写入' },
  { key: 'poolTimeoutSeconds', label: '连接池' },
]

const CONDITION_OPS: ConditionOperator[] = [
  'EQ', 'NE', 'NEQ', 'GT', 'GTE', 'LT', 'LTE',
  'IN', 'NOT_IN', 'EXISTS', 'NOT_EXISTS',
  'EMPTY', 'NOT_EMPTY', 'CONTAINS', 'REGEX',
]

const COMMON_RESPONSE_HEADERS = [
  { name: 'Content-Type', desc: '内容类型' },
  { name: 'Content-Length', desc: '内容长度' },
  { name: 'Set-Cookie', desc: '设置 Cookie' },
  { name: 'Cache-Control', desc: '缓存控制' },
  { name: 'ETag', desc: '资源标识' },
  { name: 'Location', desc: '重定向地址' },
  { name: 'X-Request-Id', desc: '请求追踪 ID' },
]

type FieldProp = 'defaultValue' | 'label' | 'remark'

interface CookieExtra {
  domain?: string
  path?: string
  expires?: string
  httpOnly?: boolean
  secure?: boolean
}

function getCookieExtra(field: InputFieldDefinition): CookieExtra {
  return (field as any)._extra ?? {}
}

function toStringRecord(obj: Record<string, unknown>): Record<string, string> {
  const result: Record<string, string> = {}
  for (const [k, v] of Object.entries(obj)) {
    result[k] = String(v ?? '')
  }
  return result
}

function configToCurl(config: HttpSourceConfig, baseUrl: string): string {
  const rm = config.requestMapping
  const query = toStringRecord((rm.query ?? {}) as Record<string, unknown>)
  const headers: Record<string, string> = {}
  for (const [k, v] of Object.entries(toStringRecord((rm.headers ?? {}) as Record<string, unknown>))) {
    headers[k] = v
  }

  let url = baseUrl + (config.path || '')
  const qs = Object.entries(query).filter(([, v]) => v).map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`).join('&')
  if (qs) url += `?${qs}`

  const parts: string[] = [`curl -X ${config.method}`]
  parts.push(`'${url}'`)
  for (const [k, v] of Object.entries(headers)) {
    parts.push(`-H '${k}: ${v}'`)
  }

  const bodyType = (rm.bodyType as string) ?? 'raw-json'
  if (config.method !== 'GET') {
    if (bodyType === 'raw-json') {
      const raw = rm.rawBody as string ?? ''
      parts.push(`-d '${raw}'`)
    } else if (bodyType === 'x-www-form-urlencoded') {
      const data = toStringRecord((rm.urlEncodedData ?? {}) as Record<string, unknown>)
      const params = Object.entries(data).filter(([, v]) => v).map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`).join('&')
      if (params) parts.push(`-d '${params}'`)
    } else if (bodyType === 'form-data') {
      const data = toStringRecord((rm.formData ?? {}) as Record<string, unknown>)
      for (const [k, v] of Object.entries(data)) {
        if (v) parts.push(`-F '${k}=${v}'`)
      }
    } else if (bodyType === 'raw-text' || bodyType === 'raw-xml') {
      const raw = rm.rawBody as string ?? ''
      if (raw) parts.push(`-d '${raw}'`)
    }
  }

  return parts.join(' \\\n  ')
}

export default Vue.extend({
  name: 'HttpSourceManagement',
  components: {
    BodyTreeEditor,
    FieldMapper,
    HeaderFieldMapper,
    HttpOutputExtractionEditor,
    JsonCodeMirror,
    ResponseSchemaNode,
  },

  data() {
    return {
      sources: [] as HttpSourceResponse[],
      systems: [] as SysResponse[],
      endpoints: [] as ServiceEndpointResponse[],
      environments: [] as EnvironmentResponse[],
      loading: true,
      httpMethods: HTTP_METHODS,
      conditionOps: CONDITION_OPS,
      timeoutFields: TIMEOUT_FIELDS,
      // filters
      methodFilter: '' as HttpMethod | '',
      sysCodeFilter: '',
      pathFilter: '',
      descFilter: '',
      page: 0,
      pageSize: 20,
      // editor
      editing: null as HttpSourceConfig | null,
      editorMode: null as 'edit' | 'view' | null,
      saving: false,
      // section toggles (el-collapse v-model)
      activeSections: ['request', 'response', 'output'] as string[],
      // request tabs
      requestTab: 'params',
      // response tabs
      responseTab: 'body',
      responseBodyView: 'tree' as 'tree' | 'preview',
      // success/failure status codes text
      successStatusCodes: '200',
      // import dialog
      importDialogVisible: false,
      importFormat: 'json' as 'json' | 'xml' | 'text' | 'headers',
      importInput: '',
      // curl
      showCurlDialog: false,
      // test
      testDialogVisible: false,
      testEnvCode: '',
      testing: false,
      testResult: null as HttpSourceTestResult | null,
      testTab: 'resp',
      // delete
      deleteDialogVisible: false,
      deleteTarget: null as string | null,
    }
  },

  computed: {
    isNew(): boolean {
      if (!this.editing) return true
      return !this.sources.some(s => s.sourceCode === this.editing!.sourceCode)
    },

    filteredSources(): HttpSourceResponse[] {
      const pathKw = this.pathFilter.trim().toLowerCase()
      const descKw = this.descFilter.trim().toLowerCase()
      return this.sources.filter(s => {
        if (this.methodFilter && s.method !== this.methodFilter) return false
        if (this.sysCodeFilter && s.sysCode !== this.sysCodeFilter) return false
        if (pathKw && !s.path.toLowerCase().includes(pathKw)) return false
        if (descKw && !s.sourceName.toLowerCase().includes(descKw)) return false
        return true
      })
    },

    pageRows(): HttpSourceResponse[] {
      const start = this.page * this.pageSize
      return this.filteredSources.slice(start, start + this.pageSize)
    },

    systemOptions(): Array<{ code: string; name: string }> {
      const seen = new Map<string, string>()
      for (const sys of this.systems) {
        seen.set(sys.sysCode, sys.sysName)
      }
      for (const ep of this.endpoints) {
        if (!seen.has(ep.sysCode)) seen.set(ep.sysCode, ep.sysCode)
      }
      return Array.from(seen.entries()).map(([code, name]) => ({ code, name }))
    },

    selectedEndpoints(): ServiceEndpointResponse[] {
      if (!this.editing) return []
      return this.endpoints.filter(ep => ep.sysCode === this.editing!.sysCode)
    },

    /* ── Request mapping helpers ── */
    rm(): Record<string, any> {
      return (this.editing?.requestMapping ?? {}) as Record<string, any>
    },
    rmQuery(): Record<string, unknown> {
      return (this.rm.query ?? {}) as Record<string, unknown>
    },
    rmQueryDesc(): Record<string, string> {
      return (this.rm._queryDesc ?? {}) as Record<string, string>
    },
    rmHeaders(): Record<string, unknown> {
      return (this.rm.headers ?? {}) as Record<string, unknown>
    },
    rmHeadersDesc(): Record<string, string> {
      return (this.rm._headersDesc ?? {}) as Record<string, string>
    },
    rmFormData(): Record<string, unknown> {
      return (this.rm.formData ?? {}) as Record<string, unknown>
    },
    rmUrlEncoded(): Record<string, unknown> {
      return (this.rm.urlEncodedData ?? {}) as Record<string, unknown>
    },
    rmUrlEncodedDesc(): Record<string, string> {
      return (this.rm._urlEncodedDesc ?? {}) as Record<string, string>
    },
    rmRawBody(): string {
      return (this.rm.rawBody as string) ?? ''
    },

    authConfig(): AuthConfig {
      return (this.rm.authConfig ?? { type: 'none' }) as AuthConfig
    },
    authType(): AuthType {
      return this.authConfig.type
    },

    bodyType(): BodyType {
      return (this.rm.bodyType as BodyType) ?? 'raw-json'
    },
    hasBody(): boolean {
      return this.editing?.method === 'POST' && this.bodyType !== 'none'
    },

    paramCount(): number {
      return Object.keys(this.rmQuery).length
    },
    headerCount(): number {
      return Object.keys(this.rmHeaders).length
    },

    /* ── Body tree editor step adapter ── */
    bodyTreeStep(): { stepId?: string; requestMapping: Record<string, unknown> } {
      return {
        stepId: undefined,
        requestMapping: this.editing?.requestMapping ?? {},
      }
    },

    /* ── Response schema ── */
    responseSchema(): InputFieldDefinition[] {
      return this.editing?.responseSchema ?? []
    },
    responseHeadersSchema(): InputFieldDefinition[] {
      return this.editing?.responseHeadersSchema ?? []
    },
    responseCookiesSchema(): InputFieldDefinition[] {
      return this.editing?.responseCookiesSchema ?? []
    },
    responseHandling(): ResponseHandling {
      return this.editing?.responseHandling ?? {
        expectedContentType: 'JSON',
        statusCode: { success: [200] },
        businessSuccess: { allOf: [] },
        businessFailure: { anyOf: [] },
      }
    },
    responseContentType(): string {
      return this.responseHandling.expectedContentType || 'JSON'
    },
    successRules(): ConditionRule[] {
      return this.responseHandling.businessSuccess?.allOf ?? []
    },
    failureRules(): ConditionRule[] {
      return this.responseHandling.businessFailure?.anyOf ?? []
    },
    responseBodyFieldCount(): number {
      return this.responseSchema.reduce((total, f) => total + countFields(f), 0)
    },
    responsePreviewText(): string {
      if (this.responseSchema.length === 0) return ''
      const obj = treeToSample(this.responseSchema)
      if (this.responseContentType === 'XML') return jsonToXml(obj)
      if (this.responseContentType === 'TEXT') return JSON.stringify(obj, null, 2)
      return JSON.stringify(obj, null, 2)
    },

    /* ── Error mapping ── */
    errorMapping(): ErrorMapping {
      return this.editing?.errorMapping ?? {
        messageTemplate: '',
        fields: {},
        fallbackMessage: '',
        exposeRawResponse: false,
      }
    },
    errorMappingFieldsJson(): string {
      return JSON.stringify(this.errorMapping.fields ?? {}, null, 2)
    },
    businessErrorMapping(): ErrorMapping {
      return this.editing?.businessErrorMapping ?? {
        messageTemplate: '',
        fields: {},
        fallbackMessage: '',
        exposeRawResponse: false,
      }
    },
    businessErrorMappingFieldsJson(): string {
      return JSON.stringify(this.businessErrorMapping.fields ?? {}, null, 2)
    },

    /* ── Retry ── */
    retryEnabled: {
      get(): boolean {
        return this.editing?.retryPolicy?.enabled ?? false
      },
      set(v: boolean) {
        if (!this.editing) return
        if (!this.editing.retryPolicy) {
          this.$set(this.editing, 'retryPolicy', { enabled: v, maxAttempts: 1, intervalMs: 1000, retryOn: [] })
        } else {
          this.$set(this.editing.retryPolicy, 'enabled', v)
        }
      },
    },
    retryPolicy(): RetryPolicy {
      return this.editing?.retryPolicy ?? { enabled: false, maxAttempts: 1, intervalMs: 1000, retryOn: [] }
    },

    /* ── Output extraction step proxy ── */
    outputStepProxy(): HttpStepDefinition {
      const e = this.editing!
      return {
        stepId: '__httpsource__',
        type: 'HTTP',
        method: e.method,
        path: e.path,
        sysCode: e.sysCode,
        timeoutConfig: e.timeoutConfig,
        requestMapping: e.requestMapping,
        httpParamMapping: {},
        responseSchema: e.responseSchema,
        responseHeadersSchema: e.responseHeadersSchema,
        responseCookiesSchema: e.responseCookiesSchema,
        responseHandling: e.responseHandling,
        outputMapping: e.outputMapping ?? {},
        outputMeta: e.outputMeta ?? null,
        enabled: true,
        dependsOn: [],
      }
    },

    /* ── Curl ── */
    curlCommandText(): string {
      if (!this.editing) return ''
      const baseUrl = this.selectedEndpoints.length > 0
        ? this.selectedEndpoints[0].baseUrl
        : 'https://api.example.com'
      return configToCurl(this.editing, baseUrl)
    },

    /* ── Test curl ── */
    testCurlCommand(): string {
      if (!this.testResult) return ''
      const req = this.testResult.request
      return buildCurlFromTestRequest(req)
    },

    importIconForFormat(): string {
      if (this.importFormat === 'json') return 'file-code'
      if (this.importFormat === 'xml') return 'file-code'
      return 'file-lines'
    },
    importPlaceholder(): string {
      if (this.importFormat === 'json') return '在此贴入 JSON 报文...'
      if (this.importFormat === 'xml') return '<?xml version="1.0"?>\n<response>\n  <code>0</code>\n</response>'
      if (this.importFormat === 'headers') return 'Content-Type: application/json\nX-Request-Id: abc123'
      return '在此贴入文本内容...'
    },
  },

  created() {
    void this.reload()
  },

  methods: {
    async reload() {
      this.loading = true
      try {
        const [s, sys, envs, eps] = await Promise.all([
          listHttpSources(),
          listSystems(),
          listEnvironments(),
          listServiceEndpoints(),
        ])
        this.sources = s
        this.systems = sys
        this.environments = envs.filter(e => e.status === 'ENABLED')
        this.endpoints = eps
      } catch (error) {
        this.$message.error(error instanceof Error ? error.message : '加载失败')
      } finally {
        this.loading = false
      }
    },

    onFilterChange() { this.page = 0 },
    onPageChange(p: number) { this.page = p - 1 },
    resetFilters() {
      this.methodFilter = ''
      this.sysCodeFilter = ''
      this.pathFilter = ''
      this.descFilter = ''
      this.page = 0
    },
    systemName(code: string): string {
      return this.systems.find(s => s.sysCode === code)?.sysName || code || '-'
    },

    // ── Editor ──
    handleNew() {
      this.openEditor(createDefaultHttpSource(), 'edit')
    },
    handleView(row: HttpSourceResponse) {
      this.openEditor(this.rowToConfig(row), 'view')
    },
    handleEdit(row: HttpSourceResponse) {
      this.openEditor(this.rowToConfig(row), 'edit')
    },
    handleCopy(row: HttpSourceResponse) {
      const existingCodes = this.sources.map(s => s.sourceCode)
      const cfg = this.rowToConfig(row)
      cfg.sourceCode = this.nextCopyCode(row.sourceCode, existingCodes)
      cfg.sourceName = `${row.sourceName} 副本`
      cfg.status = 'ENABLED'
      this.openEditor(cfg, 'edit')
    },

    rowToConfig(row: HttpSourceResponse): HttpSourceConfig {
      return {
        sourceCode: row.sourceCode,
        sourceName: row.sourceName,
        sysCode: row.sysCode,
        path: row.path,
        method: row.method,
        timeoutConfig: row.timeoutConfig,
        requestMapping: row.requestMapping ?? {},
        bodySchema: row.bodySchema ?? null,
        responseSchema: row.responseSchema ?? null,
        responseHeadersSchema: row.responseHeadersSchema ?? null,
        responseCookiesSchema: row.responseCookiesSchema ?? null,
        responseHandling: row.responseHandling ?? null,
        errorMapping: row.errorMapping ?? null,
        businessErrorMapping: row.businessErrorMapping ?? null,
        outputMapping: row.outputMapping ?? {},
        outputMeta: row.outputMeta ?? null,
        retryPolicy: row.retryPolicy ?? null,
        status: row.status,
      }
    },

    openEditor(config: HttpSourceConfig, mode: 'edit' | 'view') {
      this.editing = JSON.parse(JSON.stringify(config))
      this.editorMode = mode
      this.requestTab = 'params'
      this.responseTab = 'body'
      this.responseBodyView = 'tree'
      this.activeSections = ['request', 'response', 'output']
      const sc = config.responseHandling?.statusCode?.success ?? [200]
      this.successStatusCodes = sc.join(', ')
    },

    closeEditor() {
      this.editing = null
      this.editorMode = null
    },

    async handleSave() {
      if (!this.editing) return
      this.syncStatusCodes()
      this.saving = true
      try {
        if (this.isNew) {
          await createHttpSource(this.editing)
          this.$message.success('接口配置已创建')
        } else {
          await updateHttpSource(this.editing.sourceCode, this.editing)
          this.$message.success('接口配置已保存')
        }
        this.closeEditor()
        await this.reload()
      } catch (error) {
        this.$message.error(error instanceof Error ? error.message : '保存失败')
      } finally {
        this.saving = false
      }
    },

    syncStatusCodes() {
      if (!this.editing) return
      const codes = this.successStatusCodes.split(',').map(s => parseInt(s.trim(), 10)).filter(n => !isNaN(n))
      if (!this.editing.responseHandling) {
        this.$set(this.editing, 'responseHandling', {
          expectedContentType: 'JSON',
          statusCode: { success: codes },
          businessSuccess: { allOf: [] },
          businessFailure: { anyOf: [] },
        })
      } else {
        this.editing.responseHandling.statusCode = { success: codes }
      }
      if (this.editing.retryPolicy) {
        this.editing.retryPolicy.enabled = this.retryEnabled
      }
    },

    // ── Timeout ──
    onTimeoutChange(key: string, val: number | undefined) {
      if (!this.editing || val == null) return
      this.$set(this.editing.timeoutConfig, key, val)
    },

    // ── Request mapping updates ──
    onRmSectionChange(section: string, value: unknown) {
      if (!this.editing) return
      this.$set(this.editing.requestMapping as any, section, value)
    },

    // ── Auth ──
    onAuthTypeChange(type: string) {
      const next: AuthConfig = { type: type as AuthType }
      this.applyAuthConfig(next)
    },
    updateAuth(next: AuthConfig) {
      this.applyAuthConfig(next)
    },
    applyAuthConfig(next: AuthConfig) {
      if (!this.editing) return
      const rm = { ...this.editing.requestMapping } as Record<string, any>
      const headers = { ...(rm.headers ?? {}) } as Record<string, string>
      const query = { ...(rm.query ?? {}) } as Record<string, string>

      // Clean previous auth entries
      delete headers.Authorization
      const prev = (rm.authConfig ?? { type: 'none' }) as AuthConfig
      if (prev.type === 'apikey' && prev.key) {
        if (prev.addTo === 'query') delete query[prev.key]
        else delete headers[prev.key]
      }

      if (next.type === 'bearer' && next.token) {
        headers.Authorization = `Bearer ${next.token}`
      } else if (next.type === 'basic' && next.username) {
        headers.Authorization = `Basic {{${next.username}:${next.password ?? ''}}}`
      } else if (next.type === 'apikey' && next.key) {
        if (next.addTo === 'query') query[next.key] = next.value ?? ''
        else headers[next.key] = next.value ?? ''
      }

      rm.headers = headers
      rm.query = query
      rm.authConfig = next
      this.$set(this.editing, 'requestMapping', rm)
    },

    // ── Body type ──
    onBodyTypeChange(next: string) {
      if (!this.editing) return
      const rm = { ...this.editing.requestMapping } as Record<string, any>
      rm.bodyType = next
      const headers = { ...(rm.headers ?? {}) } as Record<string, string>
      if (next === 'raw-json') headers['Content-Type'] = 'application/json'
      else if (next === 'raw-xml') headers['Content-Type'] = 'application/xml'
      else if (next === 'raw-text') headers['Content-Type'] = 'text/plain'
      else if (next === 'x-www-form-urlencoded') headers['Content-Type'] = 'application/x-www-form-urlencoded'
      else if (next === 'form-data') delete headers['Content-Type']
      else if (next === 'none') delete headers['Content-Type']
      rm.headers = headers
      this.$set(this.editing, 'requestMapping', rm)
    },

    onBodyTreeChange(nextRm: Record<string, unknown>) {
      if (!this.editing) return
      this.$set(this.editing, 'requestMapping', nextRm)
    },

    // ── Response content type ──
    onResponseContentTypeChange(val: string) {
      if (!this.editing) return
      if (!this.editing.responseHandling) {
        this.$set(this.editing, 'responseHandling', {
          expectedContentType: val,
          statusCode: { success: [200] },
          businessSuccess: { allOf: [] },
          businessFailure: { anyOf: [] },
        })
      } else {
        this.$set(this.editing.responseHandling, 'expectedContentType', val)
      }
    },

    // ── Response schema ──
    getResponseFlatIndex(idx: number): number {
      return getFlatIndex(this.responseSchema, idx)
    },
    updateResponseFieldProp(flatIndex: number, prop: FieldProp, value: unknown) {
      if (!this.editing) return
      const next = updateFieldPropAtPath(this.responseSchema, flatIndex, prop, value)
      this.$set(this.editing, 'responseSchema', next)
    },

    // ── Response headers ──
    addResponseHeader() {
      if (!this.editing) return
      const arr = [...this.responseHeadersSchema]
      arr.push({ name: `header_${arr.length + 1}`, type: 'string', required: false, batchEnabled: false, defaultValue: '', label: '' })
      this.$set(this.editing, 'responseHeadersSchema', arr)
    },
    updateResponseHeader(index: number, prop: string, value: unknown) {
      if (!this.editing) return
      const arr = [...this.responseHeadersSchema]
      arr[index] = { ...arr[index], [prop]: value }
      this.$set(this.editing, 'responseHeadersSchema', arr)
    },
    removeResponseHeader(index: number) {
      if (!this.editing) return
      const arr = [...this.responseHeadersSchema]
      arr.splice(index, 1)
      this.$set(this.editing, 'responseHeadersSchema', arr)
    },

    // ── Response cookies ──
    addResponseCookie() {
      if (!this.editing) return
      const arr = [...this.responseCookiesSchema]
      arr.push({
        name: `cookie_${arr.length + 1}`,
        type: 'string',
        required: false,
        batchEnabled: false,
        defaultValue: '',
        label: '',
        ...( { _extra: { domain: '', path: '/', expires: '', httpOnly: false, secure: false } } as any),
      })
      this.$set(this.editing, 'responseCookiesSchema', arr)
    },
    updateResponseCookie(index: number, prop: string, value: unknown) {
      if (!this.editing) return
      const arr = [...this.responseCookiesSchema]
      arr[index] = { ...arr[index], [prop]: value }
      this.$set(this.editing, 'responseCookiesSchema', arr)
    },
    removeResponseCookie(index: number) {
      if (!this.editing) return
      const arr = [...this.responseCookiesSchema]
      arr.splice(index, 1)
      this.$set(this.editing, 'responseCookiesSchema', arr)
    },
    cookieExtra(index: number, key: string): string {
      const field = this.responseCookiesSchema[index]
      if (!field) return ''
      const extra = getCookieExtra(field)
      return (extra as any)[key] ?? ''
    },
    cookieFlag(index: number, key: string): boolean {
      const field = this.responseCookiesSchema[index]
      if (!field) return false
      const extra = getCookieExtra(field)
      return !!(extra as any)[key]
    },
    updateCookieExtra(index: number, key: string, value: string) {
      if (!this.editing) return
      const arr = [...this.responseCookiesSchema]
      const field = { ...arr[index] } as any
      if (!field._extra) field._extra = {}
      field._extra = { ...field._extra, [key]: value }
      arr[index] = field
      this.$set(this.editing, 'responseCookiesSchema', arr)
    },
    toggleCookieFlag(index: number, key: string, value: boolean) {
      if (!this.editing) return
      const arr = [...this.responseCookiesSchema]
      const field = { ...arr[index] } as any
      if (!field._extra) field._extra = {}
      field._extra = { ...field._extra, [key]: value }
      arr[index] = field
      this.$set(this.editing, 'responseCookiesSchema', arr)
    },

    // ── Business rules ──
    addSuccessRule() {
      if (!this.editing) return
      this.ensureResponseHandling()
      const rh = { ...this.editing.responseHandling! }
      rh.businessSuccess = { allOf: [...(rh.businessSuccess?.allOf ?? []), createConditionRule()] }
      this.$set(this.editing, 'responseHandling', rh)
    },
    updateSuccessRule(index: number, prop: string, value: unknown) {
      if (!this.editing) return
      const rh = { ...this.editing.responseHandling! }
      const rules = [...(rh.businessSuccess?.allOf ?? [])]
      rules[index] = { ...rules[index], [prop]: prop === 'value' ? this.parseRuleValue(value as string) : value }
      rh.businessSuccess = { allOf: rules }
      this.$set(this.editing, 'responseHandling', rh)
    },
    removeSuccessRule(index: number) {
      if (!this.editing) return
      const rh = { ...this.editing.responseHandling! }
      const rules = [...(rh.businessSuccess?.allOf ?? [])]
      rules.splice(index, 1)
      rh.businessSuccess = { allOf: rules }
      this.$set(this.editing, 'responseHandling', rh)
    },
    addFailureRule() {
      if (!this.editing) return
      this.ensureResponseHandling()
      const rh = { ...this.editing.responseHandling! }
      rh.businessFailure = { anyOf: [...(rh.businessFailure?.anyOf ?? []), createConditionRule()] }
      this.$set(this.editing, 'responseHandling', rh)
    },
    updateFailureRule(index: number, prop: string, value: unknown) {
      if (!this.editing) return
      const rh = { ...this.editing.responseHandling! }
      const rules = [...(rh.businessFailure?.anyOf ?? [])]
      rules[index] = { ...rules[index], [prop]: prop === 'value' ? this.parseRuleValue(value as string) : value }
      rh.businessFailure = { anyOf: rules }
      this.$set(this.editing, 'responseHandling', rh)
    },
    removeFailureRule(index: number) {
      if (!this.editing) return
      const rh = { ...this.editing.responseHandling! }
      const rules = [...(rh.businessFailure?.anyOf ?? [])]
      rules.splice(index, 1)
      rh.businessFailure = { anyOf: rules }
      this.$set(this.editing, 'responseHandling', rh)
    },
    ensureResponseHandling() {
      if (!this.editing) return
      if (!this.editing.responseHandling) {
        this.$set(this.editing, 'responseHandling', {
          expectedContentType: 'JSON',
          statusCode: { success: [200] },
          businessSuccess: { allOf: [] },
          businessFailure: { anyOf: [] },
        })
      }
    },
    ruleValueStr(rule: ConditionRule): string {
      if (rule.value == null) return ''
      return String(rule.value)
    },
    parseRuleValue(str: string): unknown {
      if (str === 'true') return true
      if (str === 'false') return false
      if (str === 'null') return null
      if (str !== '' && !isNaN(Number(str)) && !str.includes(' ')) return Number(str)
      return str
    },

    // ── Error mapping ──
    updateErrorMapping(prop: string, value: unknown) {
      if (!this.editing) return
      if (!this.editing.errorMapping) {
        this.$set(this.editing, 'errorMapping', { messageTemplate: '', fields: {}, fallbackMessage: '', exposeRawResponse: false })
      }
      this.$set(this.editing.errorMapping as any, prop, value)
    },
    onErrorMappingFieldsInput(val: string) {
      try {
        const parsed = JSON.parse(val)
        this.updateErrorMapping('fields', parsed)
      } catch { /* keep textarea editable */ }
    },
    updateBusinessErrorMapping(prop: string, value: unknown) {
      if (!this.editing) return
      if (!this.editing.businessErrorMapping) {
        this.$set(this.editing, 'businessErrorMapping', { messageTemplate: '', fields: {}, fallbackMessage: '', exposeRawResponse: false })
      }
      this.$set(this.editing.businessErrorMapping as any, prop, value)
    },
    onBusinessErrorMappingFieldsInput(val: string) {
      try {
        const parsed = JSON.parse(val)
        this.updateBusinessErrorMapping('fields', parsed)
      } catch { /* keep */ }
    },

    // ── Output extraction ──
    onOutputExtractionChange(updates: Partial<HttpStepDefinition>) {
      if (!this.editing) return
      if (updates.outputMapping != null) this.$set(this.editing, 'outputMapping', updates.outputMapping)
      if (updates.outputMeta != null) this.$set(this.editing, 'outputMeta', updates.outputMeta)
    },

    // ── Import ──
    openImportDialog() {
      const ct = this.responseContentType
      if (ct === 'XML') this.importFormat = 'xml'
      else if (ct === 'TEXT') this.importFormat = 'text'
      else this.importFormat = 'json'
      this.importInput = ''
      this.importDialogVisible = true
    },
    openImportHeadersDialog() {
      this.importFormat = 'headers'
      this.importInput = ''
      this.importDialogVisible = true
    },
    handleImport() {
      try {
        if (this.importFormat === 'headers') {
          this.importHeaders()
        } else if (this.importFormat === 'json') {
          this.importJson()
        } else if (this.importFormat === 'xml') {
          this.importXml()
        } else {
          // text: just save as raw sample
          if (this.editing) {
            const rm = { ...this.editing.requestMapping } as Record<string, any>
            rm._rawResponseSample = this.importInput
            this.$set(this.editing, 'requestMapping', rm)
          }
          this.$message.success('文本响应样例已保存')
        }
        this.importDialogVisible = false
        this.importInput = ''
      } catch {
        this.$message.error(`${this.importFormat.toUpperCase()} 解析失败，请检查格式`)
      }
    },
    importJson() {
      const { cleanJson, labels } = parseJsonWithComments(this.importInput)
      const parsed = JSON.parse(cleanJson) as Record<string, unknown>
      const schema = jsonToFields(parsed, labels)
      const text = JSON.stringify(parsed, null, 2)
      if (this.editing) {
        this.$set(this.editing, 'responseSchema', schema)
        const rm = { ...this.editing.requestMapping } as Record<string, any>
        rm._rawResponseSample = text
        this.$set(this.editing, 'requestMapping', rm)
      }
      this.$message.success('JSON 响应结构已解析')
    },
    importXml() {
      const tree = xmlToTree(this.importInput)
      if (tree.length === 0) throw new Error('empty')
      if (this.editing) {
        this.$set(this.editing, 'responseSchema', tree)
        const rm = { ...this.editing.requestMapping } as Record<string, any>
        rm._rawResponseSample = this.importInput
        this.$set(this.editing, 'requestMapping', rm)
      }
      this.$message.success('XML 响应结构已解析')
    },
    importHeaders() {
      const lines = this.importInput.split('\n').filter(l => l.trim())
      const fields: InputFieldDefinition[] = []
      for (const line of lines) {
        const colonIdx = line.indexOf(':')
        if (colonIdx === -1) continue
        const name = line.slice(0, colonIdx).trim()
        const value = line.slice(colonIdx + 1).trim()
        if (!name) continue
        fields.push({
          name,
          type: 'string',
          required: false,
          batchEnabled: false,
          defaultValue: value,
          label: COMMON_RESPONSE_HEADERS.find(h => h.name.toLowerCase() === name.toLowerCase())?.desc ?? '',
        })
      }
      if (fields.length > 0 && this.editing) {
        this.$set(this.editing, 'responseHeadersSchema', fields)
        this.$message.success(`已解析 ${fields.length} 个响应头`)
      } else {
        this.$message.warning('未检测到有效的 Header 行')
      }
    },

    // ── Delete ──
    onRowCommand(cmd: string, row: HttpSourceResponse) {
      if (cmd === 'copy') this.handleCopy(row)
      else if (cmd === 'curl') this.handleExportCurl(row)
      else if (cmd === 'delete') {
        this.deleteTarget = row.sourceCode
        this.deleteDialogVisible = true
      }
    },
    handleExportCurl(row: HttpSourceResponse) {
      const cfg = this.rowToConfig(row)
      const baseUrl = this.endpoints.filter(ep => ep.sysCode === cfg.sysCode).length > 0
        ? this.endpoints.filter(ep => ep.sysCode === cfg.sysCode)[0].baseUrl
        : 'https://api.example.com'
      const cmd = configToCurl(cfg, baseUrl)
      this.copyText(cmd)
    },
    async confirmDelete() {
      if (!this.deleteTarget) return
      try {
        await deleteHttpSource(this.deleteTarget)
        this.$message.success('已删除')
        this.deleteDialogVisible = false
        this.deleteTarget = null
        await this.reload()
      } catch (error) {
        this.$message.error(error instanceof Error ? error.message : '删除失败')
      }
    },

    // ── Test ──
    openTestDialog() {
      this.testDialogVisible = true
      this.testEnvCode = ''
      this.testResult = null
      this.testTab = 'resp'
    },
    async runTest() {
      if (!this.editing || !this.testEnvCode) return
      this.syncStatusCodes()
      this.testing = true
      this.testResult = null
      try {
        this.testResult = await testHttpSource(this.testEnvCode, this.editing)
        if (this.testResult.success) {
          this.$message.success('测试成功')
        } else {
          this.$message.warning('测试失败')
        }
      } catch (error) {
        this.$message.error(error instanceof Error ? error.message : '测试失败')
      } finally {
        this.testing = false
      }
    },

    // ── Curl ──
    copyCurlCommand() {
      this.copyText(this.testCurlCommand)
    },
    copyText(text: string) {
      void navigator.clipboard.writeText(text)
      this.$message.success('已复制到剪贴板')
    },

    // ── Helpers ──
    nextCopyCode(code: string, existing: string[]): string {
      let i = 1
      let candidate = `${code}_copy`
      while (existing.includes(candidate)) {
        i++
        candidate = `${code}_copy${i}`
      }
      return candidate
    },

    formatJson(value: unknown): string {
      if (value == null) return '(空)'
      if (typeof value === 'string') return value || '(空)'
      try { return JSON.stringify(value, null, 2) ?? '(空)' }
      catch { return '(无法序列化)' }
    },

    statusTagType(code: number | null | undefined): string {
      if (code == null) return 'info'
      if (code >= 200 && code < 300) return 'success'
      if (code >= 300 && code < 400) return 'warning'
      return 'danger'
    },
  },
})

/* ── curl from test request ── */

function buildCurlFromTestRequest(req: {
  method: string
  url: string
  headers: Record<string, string>
  query?: Record<string, unknown>
  body?: unknown
  bodyType?: string
}): string {
  const parts: string[] = [`curl -X ${req.method}`]
  parts.push(`'${req.url}'`)
  for (const [k, v] of Object.entries(req.headers || {})) {
    parts.push(`-H '${k}: ${v}'`)
  }
  if (req.method !== 'GET' && req.body != null) {
    const bt = req.bodyType ?? 'raw-json'
    if (bt === 'raw-json') {
      const jsonStr = typeof req.body === 'string' ? req.body : JSON.stringify(req.body)
      parts.push(`-d '${jsonStr}'`)
    } else if (bt === 'x-www-form-urlencoded' && typeof req.body === 'object') {
      const params = Object.entries(req.body as Record<string, string>)
        .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`)
        .join('&')
      parts.push(`-d '${params}'`)
    } else if (bt === 'form-data' && typeof req.body === 'object') {
      for (const [k, v] of Object.entries(req.body as Record<string, string>)) {
        parts.push(`-F '${k}=${v}'`)
      }
    } else if (typeof req.body === 'string') {
      parts.push(`-d '${req.body}'`)
    }
  }
  return parts.join(' \\\n  ')
}
</script>

<style scoped>
/* 设计令牌通过 fallback 值内联使用 */

.http-source-mgmt {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--background, #fafafa);
}

/* ── Page header ── */
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 24px;
  background: #fff;
  border-bottom: 1px solid #e5e7eb;
}
.page-header h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  color: #111827;
  letter-spacing: -0.025em;
}

/* ── Filters ── */
.filters-bar {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px 24px;
  background: linear-gradient(to bottom, #fff, #f9fafb);
  border-bottom: 1px solid #e5e7eb;
  flex-wrap: wrap;
}
.filters-bar .el-select { width: 160px; }
.filters-bar .el-input { width: 200px; }
.search-icon {
  color: #6b7280;
  line-height: 32px;
}

/* ── Table ── */
.table-wrap {
  flex: 1;
  overflow: auto;
  padding: 0 24px;
  background: #fff;
}

.cell-name {
  font-family: ui-monospace, 'SF Mono', 'Monaco', 'Cascadia Code', monospace;
  font-size: 13px;
  font-weight: 600;
  color: #111827;
  margin-bottom: 2px;
}
.cell-sub {
  font-size: 12px;
  color: #6b7280;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 280px;
}
.cell-mono {
  font-family: ui-monospace, 'SF Mono', 'Monaco', monospace;
  font-size: 12px;
  color: #6b7280;
  background: #f3f4f6;
  padding: 2px 6px;
  border-radius: 4px;
}

/* ── Method badges ── */
.method-get {
  background: linear-gradient(135deg, rgba(16, 185, 129, 0.15), rgba(16, 185, 129, 0.08)) !important;
  color: #059669 !important;
  border: 1px solid rgba(16, 185, 129, 0.3) !important;
  font-weight: 600;
}
.method-post {
  background: linear-gradient(135deg, rgba(59, 130, 246, 0.15), rgba(59, 130, 246, 0.08)) !important;
  color: #2563eb !important;
  border: 1px solid rgba(59, 130, 246, 0.3) !important;
  font-weight: 600;
}

/* ── Pagination ── */
.pager {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  padding: 12px 24px;
  background: #fff;
  border-top: 1px solid #e5e7eb;
}

/* ── Editor view ── */
.editor-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--background, #fafafa);
}

.editor-header {
  padding: 12px 24px;
  background: #fff;
  border-bottom: 1px solid #e5e7eb;
}
.header-left {
  display: flex;
  align-items: center;
  gap: 16px;
}
.header-left h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
  color: #111827;
}
.header-right {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}

.editor-body {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
}
.is-disabled {
  pointer-events: none;
  opacity: 0.7;
}

/* ── Collapse sections ── */
.editor-collapse {
  border: none;
}
.section-title {
  font-size: 15px;
  font-weight: 700;
  color: #3b82f6;
  letter-spacing: -0.01em;
}
.section-summary {
  margin-left: 12px;
}

/* ── Address bar ── */
.address-bar {
  padding: 8px;
  background: linear-gradient(to bottom, #fff, #f9fafb);
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  transition: border-color 150ms;
}
.address-bar:focus-within {
  border-color: #3b82f6;
}
.addr-method >>> .el-input__inner {
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.addr-path >>> .el-input__inner {
  font-family: ui-monospace, 'SF Mono', monospace;
  font-size: 13px;
}

.endpoint-hint {
  margin: 4px 0 0;
  padding-left: 8px;
  font-size: 11px;
  color: #6b7280;
}
.endpoint-item {
  display: inline-block;
  margin-right: 8px;
  font-family: ui-monospace, monospace;
  color: #3b82f6;
  font-weight: 500;
}

/* ── Timeout grid ── */
.timeout-grid {
  margin-top: 16px;
  padding: 16px;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
}

/* ── Request tabs ── */
.request-tabs {
  margin-top: 16px;
}
.tab-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  margin-left: 4px;
  min-width: 18px;
  height: 18px;
  padding: 0 6px;
  border-radius: 9999px;
  background: #3b82f6;
  color: #fff;
  font-size: 10px;
  font-weight: 700;
}
.tab-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-left: 4px;
  box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.8);
}
.tab-dot--green {
  background: #22c55e;
  box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.8), 0 0 8px rgba(34, 197, 94, 0.5);
}
.tab-dot--blue {
  background: #3b82f6;
  box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.8), 0 0 8px rgba(59, 130, 246, 0.5);
}

/* ── Auth section ── */
.auth-section {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.auth-type-row {
  display: flex;
  align-items: center;
  gap: 16px;
}
.auth-type-label {
  font-size: 13px;
  font-weight: 600;
  color: #111827;
}
.auth-type-select { width: 220px; }
.auth-form {
  padding: 16px;
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
}
.auth-field-label {
  display: block;
  font-size: 12px;
  font-weight: 600;
  color: #6b7280;
  margin-bottom: 4px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.mono-input >>> .el-input__inner {
  font-family: ui-monospace, 'SF Mono', monospace;
  font-size: 12px;
}

/* ── Body section ── */
.body-section {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.body-content { margin-top: 8px; }
.body-empty {
  padding: 32px;
  text-align: center;
  font-size: 13px;
  color: #6b7280;
  font-style: italic;
  background: #f9fafb;
  border: 2px dashed #e5e7eb;
  border-radius: 6px;
}

/* ── Response toolbar ── */
.resp-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
  padding: 8px;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
}
.resp-ct-select { width: 110px; }
.resp-import-btn {
  margin-left: auto;
  font-weight: 600;
}

/* ── Response tree ── */
.resp-tree {
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  background: #fff;
  overflow: hidden;
}
.resp-tree-head {
  display: grid;
  grid-template-columns: 1fr 85px 160px 1fr;
  gap: 8px;
  padding: 8px 16px;
  background: linear-gradient(to bottom, #f9fafb, #fff);
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: #6b7280;
  border-bottom: 1px solid #e5e7eb;
}
.resp-tree-body {
  max-height: 450px;
  overflow: auto;
}
.resp-tree-empty {
  padding: 32px 16px;
  text-align: center;
  font-size: 13px;
  color: #6b7280;
  font-style: italic;
}

.resp-preview {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.resp-preview-hint {
  font-size: 11px;
  color: #6b7280;
  font-weight: 500;
}
.resp-preview-text {
  padding: 16px;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  background: #f9fafb;
  font-family: ui-monospace, 'SF Mono', monospace;
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  max-height: 450px;
  overflow: auto;
  margin: 0;
}

/* ── Response Headers/Cookies toolbars ── */
.resp-headers-toolbar,
.resp-cookies-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  justify-content: flex-end;
  margin-bottom: 8px;
}
.resp-cookies-empty {
  padding: 32px;
  text-align: center;
  font-size: 13px;
  color: #6b7280;
  font-style: italic;
}
.resp-center {
  display: flex;
  justify-content: center;
  align-items: center;
}

/* ── Cookies editor grid (kept custom for 9-column layout) ── */
.resp-cookies-table {
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  background: #fff;
  overflow: hidden;
}
.resp-cookies-head {
  display: grid;
  grid-template-columns: 130px 90px 130px 110px 90px 110px 65px 65px 44px;
  gap: 4px;
  padding: 8px 16px;
  background: linear-gradient(to bottom, #f9fafb, #fff);
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: #6b7280;
  border-bottom: 1px solid #e5e7eb;
  white-space: nowrap;
}
.resp-cookies-row {
  display: grid;
  grid-template-columns: 130px 90px 130px 110px 90px 110px 65px 65px 44px;
  gap: 4px;
  align-items: center;
  padding: 8px 16px;
  border-bottom: 1px solid #e5e7eb;
}
.resp-cookies-row:hover {
  background: #f9fafb;
}
.resp-cookies-row:last-child {
  border-bottom: none;
}

.del-btn {
  color: #6b7280;
  transition: color 150ms;
}
.del-btn:hover {
  color: #ef4444;
}

/* ── Business rules (inside el-card) ── */
.inner-card {
  margin-bottom: 16px;
}
.card-header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.rules-icon {
  font-size: 15px;
  margin-right: 4px;
}
.rules-icon--success { color: #22c55e; }
.rules-icon--failure { color: #ef4444; }
.rules-empty {
  padding: 16px;
  text-align: center;
  font-size: 13px;
  color: #6b7280;
  font-style: italic;
  background: #f9fafb;
  border-radius: 4px;
}
.rule-row {
  margin-bottom: 8px;
}
.rule-row:last-child {
  margin-bottom: 0;
}
.rule-op { width: 100%; }

/* ── Error mapping (inside el-card) ── */
.em-icon {
  color: #f59e0b;
  margin-right: 4px;
}

/* ── Import dialog ── */
.import-toolbar {
  margin-bottom: 16px;
}
.import-editor {
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  overflow: hidden;
}
.import-textarea {
  width: 100%;
  height: 320px;
  border: none;
  padding: 16px;
  font-family: ui-monospace, 'SF Mono', monospace;
  font-size: 12px;
  line-height: 1.6;
  resize: vertical;
  outline: none;
  background: #f9fafb;
}

/* ── Test dialog ── */
.test-env-row {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 16px;
  padding: 16px;
  background: #f9fafb;
  border-radius: 6px;
}
.test-result-area {
  margin-top: 8px;
}
.test-metrics {
  display: flex;
  align-items: center;
  gap: 24px;
  margin-bottom: 16px;
  padding: 8px 16px;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
}
.metric-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}
.metric-label {
  font-weight: 600;
  color: #6b7280;
}
.metric-value {
  font-family: ui-monospace, monospace;
  font-weight: 600;
  color: #111827;
}

.test-block {
  margin-bottom: 16px;
  padding: 16px;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
}
.test-block-title {
  font-size: 13px;
  font-weight: 700;
  color: #111827;
  margin-bottom: 8px;
  padding-bottom: 4px;
  border-bottom: 1px solid #e5e7eb;
  display: flex;
  align-items: center;
  gap: 8px;
}
.test-block--error {
  border-left: 4px solid #ef4444;
  background: linear-gradient(to right, rgba(239, 68, 68, 0.05), transparent);
}
.test-block-text {
  font-size: 13px;
  color: #6b7280;
  margin: 0;
  line-height: 1.6;
}
.test-pre {
  padding: 16px;
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 4px;
  font-family: ui-monospace, 'SF Mono', monospace;
  font-size: 12px;
  line-height: 1.6;
  overflow-x: auto;
  max-height: 320px;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
}
.test-curl {
  white-space: pre-wrap;
}
.test-body-type {
  font-size: 11px;
  font-weight: 500;
  color: #6b7280;
  font-family: ui-monospace, monospace;
  background: #f3f4f6;
  padding: 2px 6px;
  border-radius: 4px;
}
.test-grid-2col {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}
.test-error-type {
  font-size: 12px;
  font-family: ui-monospace, monospace;
  color: #ef4444;
  font-weight: 600;
  margin: 0 0 4px;
}
.test-request-area {
  margin-top: 8px;
}
.copy-btn {
  margin-left: auto;
  font-size: 11px;
}
.mono-cell {
  font-family: ui-monospace, monospace;
  font-size: 12px;
  font-weight: 500;
}

/* ── Curl export ── */
.curl-export-pre {
  padding: 24px;
  background: linear-gradient(to bottom, #f9fafb, #fff);
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  font-family: ui-monospace, 'SF Mono', monospace;
  font-size: 12px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 450px;
  overflow: auto;
  margin: 0;
}

/* ── Utility classes ── */
.menu-icon {
  margin-right: 8px;
  opacity: 0.7;
}
.cmd-danger {
  color: #ef4444 !important;
}
.ml-1 { margin-left: 4px; }
.text-muted { color: #6b7280; }
.text-muted-sm {
  color: #6b7280;
  font-size: 12px;
}
.text-success { color: #22c55e; }
.text-danger { color: #ef4444; }

/* ── Element UI overrides ── */
.editor-body >>> .el-form-item {
  margin-bottom: 16px;
}
.editor-body >>> .el-form-item__label {
  font-weight: 600;
  color: #111827;
}
.editor-body >>> .el-tabs__item {
  font-weight: 600;
}
.editor-body >>> .el-input__inner {
  transition: border-color 150ms, box-shadow 150ms;
}
.editor-body >>> .el-input__inner:focus {
  border-color: #3b82f6;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}
.editor-body >>> .el-select .el-input__inner {
  cursor: pointer;
}
.editor-body >>> .el-radio-button__inner {
  font-weight: 600;
}
.editor-collapse >>> .el-collapse-item__header {
  background: transparent;
  font-size: 15px;
  border-bottom: 2px solid transparent;
  border-image: linear-gradient(to right, #3b82f6, transparent) 1;
  padding-bottom: 8px;
}
.editor-collapse >>> .el-collapse-item__wrap {
  background: transparent;
  border-bottom: none;
  padding: 16px 0;
}
.editor-collapse >>> .el-collapse-item__content {
  padding-bottom: 0;
}
.inner-card >>> .el-card__header {
  padding: 12px 16px;
  font-weight: 700;
  font-size: 14px;
  color: #111827;
  background: #f9fafb;
}
</style>
