import axios from 'axios';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:5000';

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 300000, // 5分钟超时，因为AI Agent处理可能需要较长时间
  headers: {
    'Content-Type': 'application/json',
  },
});

export interface RunAgentRequest {
  original_query: string;
  topic?: string;
  methodology?: string;
  results?: string;
  messages?: any[];
}

export interface RunAgentResponse {
  success: boolean;
  data?: {
    latex_revision: string;
    topic: string;
    results: string;
    summary: string;
    new_idea: string;
    motivation: string;
    final_state?: any;
  };
  error?: string;
}

export interface WorkflowStep {
  id: string;
  name: string;
  status: 'pending' | 'running' | 'completed' | 'error';
}

export interface ProgressEvent {
  step: string;
  status: string;
  steps: WorkflowStep[];
  data?: any;
}

export type EventSourceCallback = (event: MessageEvent) => void;

export const checkHealth = async (): Promise<void> => {
  try {
    const response = await api.get('/api/health');
    if (response.data.status === 'ok') {
      return;
    }
    throw new Error('服务状态异常');
  } catch (error: any) {
    throw new Error('无法连接到后端服务');
  }
};

export const runAgent = async (request: RunAgentRequest): Promise<RunAgentResponse> => {
  try {
    const response = await api.post<RunAgentResponse>('/api/run-agent', request);
    return response.data;
  } catch (error: any) {
    if (error.response) {
      // 服务器返回了错误响应
      throw new Error(error.response.data.error || '服务器错误');
    } else if (error.request) {
      // 请求已发出但没有收到响应
      throw new Error('无法连接到服务器，请检查后端服务是否运行');
    } else {
      // 其他错误
      throw new Error(error.message || '请求失败');
    }
  }
};

export const runAgentStream = (
  request: RunAgentRequest,
  callbacks: {
    onStart?: (data: any) => void;
    onProgress?: (event: ProgressEvent) => void;
    onComplete?: (data: any) => void;
    onError?: (error: string) => void;
  }
): { close: () => void } => {
  // 由于EventSource不支持POST，我们使用fetch + ReadableStream
  const controller = new AbortController();
  
  let currentEventType = '';
  
  fetch(`${API_BASE_URL}/api/run-agent-stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(request),
    signal: controller.signal,
  })
    .then(response => {
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      
      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      
      if (!reader) {
        throw new Error('无法读取响应流');
      }
      
      let buffer = '';
      
      const processStream = (): Promise<void> => {
        return reader.read().then(({ done, value }) => {
          if (done) {
            return Promise.resolve();
          }
          
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || ''; // 保留不完整的行
          
          for (const line of lines) {
            if (line.trim() === '') {
              // 空行表示一个事件结束，处理之前累积的数据
              continue;
            }
            
            if (line.startsWith('event: ')) {
              currentEventType = line.substring(7).trim();
              continue;
            }
            
            if (line.startsWith('data: ')) {
              const dataStr = line.substring(6).trim();
              if (!dataStr) continue;
              
              try {
                const data = JSON.parse(dataStr);
                
                // 根据事件类型调用相应的回调
                switch (currentEventType) {
                  case 'start':
                    callbacks.onStart?.(data);
                    break;
                  case 'progress':
                    callbacks.onProgress?.(data as ProgressEvent);
                    break;
                  case 'complete':
                    callbacks.onComplete?.(data);
                    break;
                  case 'error':
                    callbacks.onError?.(data.error || '未知错误');
                    break;
                  default:
                    // 如果没有事件类型，尝试根据数据内容判断
                    if (data.steps) {
                      callbacks.onProgress?.(data as ProgressEvent);
                    } else if (data.success !== undefined) {
                      if (data.success) {
                        callbacks.onComplete?.(data);
                      } else {
                        callbacks.onError?.(data.error || '未知错误');
                      }
                    } else if (data.query) {
                      callbacks.onStart?.(data);
                    }
                }
              } catch (e) {
                console.error('解析SSE数据失败:', e, '数据:', dataStr);
              }
            }
          }
          
          return processStream();
        });
      };
      
      return processStream();
    })
    .catch(error => {
      if (error.name !== 'AbortError') {
        callbacks.onError?.(error.message || '流式请求失败');
      }
    });
  
  // 返回一个可以取消的对象
  return {
    close: () => controller.abort(),
  };
};

export default api;
