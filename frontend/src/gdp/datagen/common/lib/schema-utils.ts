import type { InputFieldDefinition, InputFieldType } from "./types";

export interface FlatSchemaEntry {
  label: string;
  name: string;
  path: string;
  type: string;
  depth: number;
  fieldLabel: string;
  fieldRemark: string;
}

/**
 * Converts a plain JS object into an array of InputFieldDefinitions.
 */
export function jsonToFields(
  obj: Record<string, unknown>,
  labels: Record<string, string> = {},
): InputFieldDefinition[] {
  if (typeof obj !== "object" || obj === null) return [];

  return Object.entries(obj).map(([key, value]) => {
    let type: InputFieldType = "string";
    let children: InputFieldDefinition[] | undefined;

    if (Array.isArray(value)) {
      type = "array";
      if (value.length > 0 && typeof value[0] === "object") {
        children = jsonToFields(value[0] as Record<string, unknown>, labels);
      }
    } else if (typeof value === "object" && value !== null) {
      type = "object";
      children = jsonToFields(value as Record<string, unknown>, labels);
    } else if (typeof value === "number") {
      type = "number";
    } else if (typeof value === "boolean") {
      type = "boolean";
    }

    return {
      name: key,
      label: labels[key] ?? "",
      type,
      required: false,
      batchEnabled: false,
      defaultValue:
        type !== "object" && type !== "array" ? value : undefined,
      children: children?.length ? children : undefined,
    };
  });
}

/**
 * Parses JSON string that contains // comments and maps them to field names.
 */
export function parseJsonWithComments(input: string): {
  cleanJson: string;
  labels: Record<string, string>;
} {
  const labels: Record<string, string> = {};
  const lines = input.split("\n");
  const cleanLines = lines.map((line) => {
    const match = /^\s*"([^"]+)"\s*:.*?\/\/\s*(.*)$/.exec(line);
    if (match) {
      const key = match[1];
      const comment = match[2]?.trim();
      if (key && comment) {
        labels[key] = comment;
      }
    }
    return line.replace(/\/\/.*$/, "");
  });

  return {
    cleanJson: cleanLines.join("\n"),
    labels,
  };
}

/**
 * Flattens the schema tree into a list of paths for selectors.
 */
export function flattenSchema(
  fields: InputFieldDefinition[],
  parentPath = "$",
  depth = 0,
): FlatSchemaEntry[] {
  const list: FlatSchemaEntry[] = [];
  fields.forEach((f) => {
    const currentPath =
      f.type === "array"
        ? `${parentPath}.${f.name}[*]`
        : `${parentPath}.${f.name}`;
    list.push({
      label: f.label ? `${f.name} (${f.label})` : f.name,
      name: f.name,
      path: currentPath,
      type: f.type,
      depth,
      fieldLabel: f.label ?? "",
      fieldRemark: f.remark ?? "",
    });
    if (f.children) {
      list.push(...flattenSchema(f.children, currentPath, depth + 1));
    }
  });
  return list;
}

/**
 * Count total fields in a tree branch (including the root).
 */
export function countFields(field: InputFieldDefinition): number {
  let n = 1;
  if (field.children) {
    field.children.forEach((c) => {
      n += countFields(c);
    });
  }
  return n;
}

/**
 * Compute the flat index for the Nth top-level field in the flattened list.
 */
export function getFlatIndex(
  fields: InputFieldDefinition[],
  topIndex: number,
): number {
  let count = 0;
  for (let i = 0; i < topIndex; i++) {
    count += countFields(fields[i]!);
  }
  return count;
}

/**
 * Update a field property at a specific flat index within the schema tree.
 * Returns a new array (immutable update).
 */
export function updateFieldPropAtPath(
  schema: InputFieldDefinition[],
  flatIndex: number,
  prop: "defaultValue" | "label" | "remark" | "name" | "type",
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  value: any,
): InputFieldDefinition[] {
  const indexPaths: number[][] = [];
  let count = 0;
  const buildPaths = (
    fields: InputFieldDefinition[],
    currentPath: number[],
  ) => {
    for (let i = 0; i < fields.length; i++) {
      indexPaths.push([...currentPath, i]);
      if (count === flatIndex) return;
      count++;
      if (fields[i]!.children) {
        buildPaths(fields[i]!.children!, [...currentPath, i]);
      }
    }
  };
  buildPaths(schema, []);
  const targetPath = indexPaths[flatIndex];
  if (!targetPath) return schema;

  const next = JSON.parse(JSON.stringify(schema)) as InputFieldDefinition[];
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let field: any = next;
  for (let i = 0; i < targetPath.length - 1; i++) {
    field = field[targetPath[i]!].children;
  }
  field[targetPath[targetPath.length - 1]!][prop] = value;
  return next;
}
