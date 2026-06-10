// Body-tree ↔ serialized payload helpers, shared by the body-tree editor.
//
// Framework-agnostic; ported verbatim from the React `body-tree-editor`'s
// inline helpers so the Vue component stays focused on rendering.

import type { InputFieldDefinition } from "./types";
import { formatUnknownValue, isRecord } from "./value-utils";
import { isVariableRef } from "./variable-utils";

/** Restore a bodyTree (InputFieldDefinition[]) back into a plain JSON object. */
export function treeToJson(tree: InputFieldDefinition[]): Record<string, unknown> {
  const obj: Record<string, unknown> = {};
  for (const field of tree) {
    if (field.type === "object" && field.children) {
      obj[field.name] = treeToJson(field.children);
    } else if (field.type === "array" && field.children) {
      obj[field.name] = [treeToJson(field.children)];
    } else {
      const val = field.defaultValue;
      if (val === "" || val === null || val === undefined) {
        obj[field.name] = "";
      } else if (typeof val === "string" && isVariableRef(val)) {
        obj[field.name] = val;
      } else if (
        typeof val === "string" &&
        val !== "" &&
        !isNaN(Number(val)) &&
        !val.includes(" ")
      ) {
        obj[field.name] = Number(val);
      } else if (val === "true") {
        obj[field.name] = true;
      } else if (val === "false") {
        obj[field.name] = false;
      } else {
        obj[field.name] = val;
      }
    }
  }
  return obj;
}

/**
 * Build a preview sample object from a schema tree. Like {@link treeToJson} but
 * without the variable-reference passthrough — used by the response editor to
 * render a formatted JSON/XML sample of the declared response structure.
 */
export function treeToSample(tree: InputFieldDefinition[]): Record<string, unknown> {
  const obj: Record<string, unknown> = {};
  for (const field of tree) {
    if (field.type === "object" && field.children) {
      obj[field.name] = treeToSample(field.children);
    } else if (field.type === "array" && field.children) {
      obj[field.name] = [treeToSample(field.children)];
    } else {
      const val = field.defaultValue;
      if (val === "" || val === null || val === undefined) {
        obj[field.name] = "";
      } else if (
        typeof val === "string" &&
        val !== "" &&
        !isNaN(Number(val)) &&
        !val.includes(" ")
      ) {
        obj[field.name] = Number(val);
      } else if (val === "true") {
        obj[field.name] = true;
      } else if (val === "false") {
        obj[field.name] = false;
      } else {
        obj[field.name] = val;
      }
    }
  }
  return obj;
}

/** Minimal JSON → XML serializer (used for the XML format preview). */
export function jsonToXml(obj: Record<string, unknown>, indent = 0): string {
  const pad = "  ".repeat(indent);
  const lines: string[] = [];
  if (indent === 0) lines.push('<?xml version="1.0" encoding="UTF-8"?>');
  for (const [key, value] of Object.entries(obj)) {
    if (isRecord(value)) {
      lines.push(`${pad}<${key}>`);
      lines.push(jsonToXml(value, indent + 1));
      lines.push(`${pad}</${key}>`);
    } else if (Array.isArray(value)) {
      for (const item of value) {
        if (isRecord(item)) {
          lines.push(`${pad}<${key}>`);
          lines.push(jsonToXml(item, indent + 1));
          lines.push(`${pad}</${key}>`);
        } else {
          lines.push(`${pad}<${key}>${formatUnknownValue(item)}</${key}>`);
        }
      }
    } else {
      lines.push(`${pad}<${key}>${formatUnknownValue(value)}</${key}>`);
    }
  }
  return lines.join("\n");
}

/** Parse an XML string into InputFieldDefinition[]. */
export function xmlToTree(xmlStr: string): InputFieldDefinition[] {
  const parser = new DOMParser();
  const doc = parser.parseFromString(xmlStr.trim(), "text/xml");

  const errorNode = doc.querySelector("parsererror");
  if (errorNode) throw new Error(errorNode.textContent ?? "XML parse error");

  function elementToField(el: Element): InputFieldDefinition {
    const children = Array.from(el.children);
    if (children.length > 0) {
      const tagNames = new Set(children.map((c) => c.tagName));
      const isArray = tagNames.size === 1 && children.length > 1;

      if (isArray) {
        return {
          name: el.tagName,
          type: "array",
          required: false,
          batchEnabled: false,
          children: [elementToField(children[0]!)],
        };
      }

      return {
        name: el.tagName,
        type: "object",
        required: false,
        batchEnabled: false,
        children: children.map(elementToField),
      };
    }

    const text = el.textContent?.trim() ?? "";
    let type: InputFieldDefinition["type"] = "string";
    if (text !== "" && !isNaN(Number(text)) && !text.includes(" ")) {
      type = "number";
    } else if (text === "true" || text === "false") {
      type = "boolean";
    }

    return {
      name: el.tagName,
      type,
      required: false,
      batchEnabled: false,
      defaultValue: text,
    };
  }

  const root = doc.documentElement;
  if (!root) return [];

  return [elementToField(root)];
}
