import { message } from "antd";

export const notifySuccess = (text) => message.success(text);
export const notifyError = (text) => message.error(text);