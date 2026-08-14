export const assistantDataBoundary = {
  summary: 'Molecular Copilot 使用服务器配置的第三方大模型服务，当前发布配置为 DeepSeek。用户对话及必要的任务摘要可能发送给 DeepSeek；所有计算仍为 logical_virtual_qpu，is_real_qpu=false，非真实 QPU。',
  sent: [
    '用户对话与 Assistant 历史消息。',
    '六个受控工具的定义，用于生成回答和选择工具。',
    '当前用户任务结果的紧凑摘要，不包含完整执行工件。',
  ],
  excluded: [
    'JWT、DeepSeek API Key、Cookie 或其他凭据。',
    '完整 QASM、完整 routed execution plan 与 VQE 迭代历史。',
  ],
  controls: [
    'DeepSeek 只负责生成回答和选择受控工具，不能直接获得 HTTP、Shell、SQL、文件系统或任意代码执行能力。',
    'Workflow、Molecular Study 与 LiH Bond Scan 草稿仍必须由用户确认；模型不能绕过确认直接创建任务。',
  ],
}
