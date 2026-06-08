"use client";

import { EyeIcon } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";

import type { IdentifierReferenceConfig } from "../common/lib/types";
import { formatUnknownValue } from "../common/lib/value-utils";

import { StatusBadge } from "./config-helpers";

const USAGE_ALL = ["发送前", "报文节点", "预期结果", "发送后处理"];
const USAGE_SQL = ["发送前：SQL", "发送后：SQL", "预期结果校验：数据库校验SQL"];

const BUILTIN_REFERENCES: IdentifierReferenceConfig[] = [
  {
    refCode: "TIME",
    refName: "时间偏移",
    refType: "TIME",
    syntax: "${type(pattern)offset}",
    description: "生成各种格式的时间。type 为空时默认 NOW，不进行偏移。",
    usageScope: USAGE_ALL,
    parameters: [
      {
        name: "type",
        description: "可为空，默认 NOW。可偏移类型：YEAR、MONTH、DATE、HOUR、MINUTE。",
        required: false,
        defaultValue: "NOW",
      },
      {
        name: "pattern",
        description: "替换后的时间格式。Y 年份，M 月份，D 日期，H 24小时，h 12小时，m 分钟，s 秒，S 毫秒。",
        required: true,
      },
      {
        name: "offset",
        description: "时间偏移量。+ 向后偏移，- 向前偏移。使用偏移类型时必须填写，即使偏移量为 0。",
        required: false,
        defaultValue: 0,
      },
    ],
    examples: [
      {
        expression: "${YEAR(yyyyMMdd)+4}",
        description: "获取 4 年后的当天。YEAR 代表年偏移，+4 代表 4 年后。",
      },
      {
        expression: "${DATE(yyyyMMdd HH:mm:ss)+2}",
        description: "获取 2 天后的当前时间。DATE 代表天数偏移，+2 代表 2 天后。",
      },
      {
        expression: "${HOUR(yyyyMMdd HH:mm:ss)+1}",
        description: "获取 1 小时后的当前时间。HOUR 代表小时偏移，+1 代表 1 小时后。",
      },
    ],
    status: "ENABLED",
    remark: "时间格式按后端解析器约定处理。",
  },
  {
    refCode: "MATCHER",
    refName: "正则表达式",
    refType: "MATCHER",
    syntax: "#[Matcher(参数1,参数2,参数3,参数4)]",
    description: "根据正则表达式获取符合正则规则的数据。",
    usageScope: USAGE_ALL,
    parameters: [
      { name: "参数1", description: "被正则表达式截取的字段，支持响应报文字段、数据库字段、特殊标识引用字段等。", required: true },
      { name: "参数2", description: "正则表达式。若正则表达式存在特殊字符，需要按解析器约定转义。", required: true },
      { name: "参数3", description: "默认 0。正则表达式 group 使用，后续会扩展。", required: false, defaultValue: 0 },
      { name: "参数4", description: "索引 N。符合正则匹配的字段有多个时，根据索引取第 N 个。", required: true },
    ],
    examples: [
      {
        expression: "#[Matcher(ReMessage,\\d{6},0,1)]",
        description: "根据表达式 \\d{6} 去 ReMessage 匹配，获取第 1 个符合匹配的字符串。",
      },
    ],
    status: "ENABLED",
    remark: "",
  },
  {
    refCode: "TPN",
    refName: "定制化分片键",
    refType: "TPN",
    syntax: '${TPN("参数1")}',
    description: "根据入参获取数据库 partNo 用于数据库操作。目前暂时支持简单分片，多字段分片暂不支持。",
    usageScope: USAGE_SQL,
    parameters: [
      { name: "参数1", description: "用于计算 partNo 的单字段入参。", required: true },
    ],
    examples: [
      {
        expression: 'select * from table where card_no = "123456789" and part_no = "${TPN("123456789")}"',
        description: "使用 ParritionUtil.mod8192WithHash 根据卡号计算分片键。",
      },
    ],
    status: "ENABLED",
    remark: "核心下移数据库。",
  },
  {
    refCode: "LOGIN",
    refName: "登录信息",
    refType: "LOGIN",
    syntax: "${LOGIN('*')}",
    description: "* 为 Token 时获取登录接口 token 值；* 为 Cookie 时获取登录接口 cookie 值。",
    usageScope: USAGE_ALL,
    parameters: [
      { name: "*", description: "支持 Token、Cookie。", required: true },
    ],
    examples: [
      { expression: "${LOGIN('Token')}", description: "获取登录接口返回的 token 值。" },
      { expression: "${LOGIN('Cookie')}", description: "获取登录接口返回的 cookie 值。" },
    ],
    status: "ENABLED",
    remark: "交易环境后自动封装的数据，只有交易环境中存在登录信息且登录成功才能使用。",
  },
  {
    refCode: "BASE64",
    refName: "Base64",
    refType: "BASE64",
    syntax: "${ToBase64[xxxx]}",
    description: "将中括号内的内容转换为 Base64。",
    usageScope: USAGE_ALL,
    parameters: [
      { name: "xxxx", description: "需要进行 Base64 编码的原始内容。", required: true },
    ],
    examples: [
      { expression: "${ToBase64[admin:123456]}", description: "将 admin:123456 转换为 Base64。" },
    ],
    status: "ENABLED",
    remark: "",
  },
];

export function IdentifierReferencesTab() {
  const [selected, setSelected] = useState<IdentifierReferenceConfig | null>(null);

  return (
    <div className="mt-4 space-y-4">
      <div className="rounded-md border">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b bg-muted/50">
              <th className="px-3 py-2 text-left font-medium">标识编码</th>
              <th className="px-3 py-2 text-left font-medium">标识名称</th>
              <th className="px-3 py-2 text-left font-medium">语法</th>
              <th className="px-3 py-2 text-left font-medium">可用位置</th>
              <th className="px-3 py-2 text-left font-medium">状态</th>
              <th className="w-20 px-3 py-2 text-right font-medium">操作</th>
            </tr>
          </thead>
          <tbody>
            {BUILTIN_REFERENCES.map((item) => (
              <tr key={item.refCode} className="border-b last:border-b-0">
                <td className="px-3 py-2 font-mono text-xs">{item.refCode}</td>
                <td className="px-3 py-2">{item.refName}</td>
                <td className="px-3 py-2 font-mono text-xs">{item.syntax}</td>
                <td className="px-3 py-2">
                  <div className="flex flex-wrap gap-1">
                    {item.usageScope.slice(0, 2).map((scope) => (
                      <Badge key={scope} variant="outline" className="text-[10px]">
                        {scope}
                      </Badge>
                    ))}
                    {item.usageScope.length > 2 && (
                      <Badge variant="secondary" className="text-[10px]">
                        +{item.usageScope.length - 2}
                      </Badge>
                    )}
                  </div>
                </td>
                <td className="px-3 py-2">
                  <StatusBadge status={item.status} />
                </td>
                <td className="px-3 py-2 text-right">
                  <Button
                    variant="ghost"
                    size="icon"
                    className="size-7"
                    onClick={() => setSelected(item)}
                  >
                    <EyeIcon className="size-3.5" />
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Dialog open={!!selected} onOpenChange={(open) => !open && setSelected(null)}>
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle>
              {selected?.refName}
              {selected && (
                <span className="ml-2 font-mono text-sm text-muted-foreground">
                  {selected.refCode}
                </span>
              )}
            </DialogTitle>
          </DialogHeader>
          {selected && (
            <ScrollArea className="max-h-[70vh] pr-4">
              <div className="space-y-4 text-sm">
                <DetailBlock title="语法" value={selected.syntax} mono />
                <DetailBlock title="说明" value={selected.description} />
                <div className="space-y-2">
                  <div className="text-xs font-semibold text-muted-foreground">参数</div>
                  <div className="rounded-md border">
                    {selected.parameters.map((param) => (
                      <div
                        key={param.name}
                        className="grid grid-cols-[120px_80px_1fr] gap-2 border-b px-3 py-2 last:border-b-0"
                      >
                        <div className="font-mono text-xs">{param.name}</div>
                        <div className="text-xs text-muted-foreground">
                          {param.required ? "必填" : `默认 ${formatUnknownValue(param.defaultValue, "-")}`}
                        </div>
                        <div className="text-xs">{param.description}</div>
                      </div>
                    ))}
                  </div>
                </div>
                <div className="space-y-2">
                  <div className="text-xs font-semibold text-muted-foreground">使用位置</div>
                  <div className="flex flex-wrap gap-1">
                    {selected.usageScope.map((scope) => (
                      <Badge key={scope} variant="outline">
                        {scope}
                      </Badge>
                    ))}
                  </div>
                </div>
                <div className="space-y-2">
                  <div className="text-xs font-semibold text-muted-foreground">示例</div>
                  <div className="space-y-2">
                    {selected.examples.map((example) => (
                      <div key={example.expression} className="rounded-md border bg-muted/30 p-3">
                        <div className="break-all font-mono text-xs">{example.expression}</div>
                        <div className="mt-1 text-xs text-muted-foreground">{example.description}</div>
                      </div>
                    ))}
                  </div>
                </div>
                {selected.remark && <DetailBlock title="备注" value={selected.remark} />}
              </div>
            </ScrollArea>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

function DetailBlock({
  title,
  value,
  mono = false,
}: {
  title: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="space-y-1">
      <div className="text-xs font-semibold text-muted-foreground">{title}</div>
      <div className={mono ? "break-all font-mono text-xs" : "text-sm"}>{value}</div>
    </div>
  );
}
