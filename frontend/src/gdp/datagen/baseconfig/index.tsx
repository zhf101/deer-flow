"use client";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  TooltipProvider,
} from "@/components/ui/tooltip";

import { DatasourcesTab } from "./datasources-tab";
import { ServiceEndpointsTab } from "./endpoints-tab";
import { EnvironmentsTab } from "./environments-tab";
import { IdentifierReferencesTab } from "./identifier-references-tab";
import { SystemsTab } from "./systems-tab";

export function ConfigManagement() {
  return (
    <TooltipProvider delayDuration={300}>
    <div className="flex h-full flex-col p-6">
      <div className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight">配置管理</h1>
        <p className="text-muted-foreground mt-1 text-sm">
          管理环境、系统、服务端点、数据源和标识引用配置
        </p>
      </div>

      <Tabs defaultValue="environments" className="flex-1">
        <TabsList>
          <TabsTrigger value="environments">环境</TabsTrigger>
          <TabsTrigger value="systems">系统</TabsTrigger>
          <TabsTrigger value="endpoints">服务端点</TabsTrigger>
          <TabsTrigger value="datasources">数据源</TabsTrigger>
          <TabsTrigger value="identifier-references">标识引用</TabsTrigger>
        </TabsList>

        <TabsContent value="environments">
          <EnvironmentsTab />
        </TabsContent>
        <TabsContent value="systems">
          <SystemsTab />
        </TabsContent>
        <TabsContent value="endpoints">
          <ServiceEndpointsTab />
        </TabsContent>
        <TabsContent value="datasources">
          <DatasourcesTab />
        </TabsContent>
        <TabsContent value="identifier-references">
          <IdentifierReferencesTab />
        </TabsContent>
      </Tabs>
    </div>
    </TooltipProvider>
  );
}
