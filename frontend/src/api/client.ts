import axios from "axios";

/** 所有请求统一走 /api 前缀：开发环境由 Vite proxy 重写到后端，生产环境由 nginx 转发 */
export const apiClient = axios.create({
  baseURL: "/api",
  timeout: 90_000,
  headers: {
    "Content-Type": "application/json",
  },
});

/** 从 axios 错误中提取可读信息 */
export function extractErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail;
    if (typeof detail === "string") {
      return detail;
    }
    if (Array.isArray(detail) && detail.length > 0) {
      return String(detail[0]?.msg ?? "请求参数错误");
    }
    return error.message;
  }
  return error instanceof Error ? error.message : String(error);
}
