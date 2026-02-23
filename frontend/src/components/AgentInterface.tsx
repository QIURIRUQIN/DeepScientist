import React, { useState, useRef } from 'react';
import './AgentInterface.css';
import { checkHealth, runAgentStream, WorkflowStep, ProgressEvent } from '../services/api';
import WorkflowLogs, { LogEntry } from './WorkflowLogs';

interface AgentResponse {
  success: boolean;
  data?: {
    latex_revision: string;
    topic: string;
    results: string;
    summary: string;
    new_idea: string;
    motivation: string;
  };
  error?: string;
}

const AgentInterface: React.FC = () => {
  const [query, setQuery] = useState('');
  const [topic, setTopic] = useState('agent');
  const [methodology, setMethodology] = useState('LLM, Agent, Tool, Memory');
  const [loading, setLoading] = useState(false);
  const [response, setResponse] = useState<AgentResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [healthStatus, setHealthStatus] = useState<string>('检查中...');
  const [workflowSteps, setWorkflowSteps] = useState<WorkflowStep[]>([]);
  const [currentStep, setCurrentStep] = useState<string>('');
  const [streamAbortController, setStreamAbortController] = useState<AbortController | null>(null);
  const [workflowLogs, setWorkflowLogs] = useState<LogEntry[]>([]);

  React.useEffect(() => {
    // 检查服务健康状态
    checkHealth()
      .then(() => setHealthStatus('服务正常'))
      .catch(() => setHealthStatus('服务异常'));
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!query.trim()) {
      setError('请输入研究问题');
      return;
    }

    setLoading(true);
    setError(null);
    setResponse(null);
    setWorkflowSteps([]);
    setCurrentStep('');
    setWorkflowLogs([]); // 清空日志

    // 创建AbortController用于取消请求
    const controller = new AbortController();
    setStreamAbortController(controller);

    try {
      // 使用流式API
      const stream = runAgentStream(
        {
          original_query: query,
          topic: topic,
          methodology: methodology,
        },
        {
          onStart: (data) => {
            console.log('开始:', data);
            if (data.steps) {
              setWorkflowSteps(data.steps);
            }
          },
          onProgress: (event: ProgressEvent) => {
            console.log('进度:', event);
            if (event.steps) {
              setWorkflowSteps(event.steps);
            }
            if (event.step) {
              setCurrentStep(event.step);
            }
            
            // 添加日志条目
            if (event.step && event.data) {
              const logEntry: LogEntry = {
                step: event.step,
                timestamp: new Date().toLocaleTimeString('zh-CN'),
                message: event.data.message || '',
                data: event.data
              };
              setWorkflowLogs(prev => [...prev, logEntry]);
            }
          },
          onComplete: (data) => {
            console.log('完成:', data);
            setResponse({
              success: true,
              data: data.data,
            });
            setLoading(false);
            setStreamAbortController(null);
          },
          onError: (errorMsg) => {
            console.error('错误:', errorMsg);
            setError(errorMsg);
            setLoading(false);
            setStreamAbortController(null);
          },
        }
      );

      // 如果stream有close方法，保存它以便取消
      if (stream && typeof stream.close === 'function') {
        // stream已经处理了AbortController
      }
    } catch (err: any) {
      setError(err.message || '请求失败，请稍后重试');
      setLoading(false);
      setStreamAbortController(null);
    }
  };

  const handleCancel = () => {
    if (streamAbortController) {
      streamAbortController.abort();
      setStreamAbortController(null);
      setLoading(false);
      setError('已取消');
    }
  };

  const getStepStatusIcon = (status: string) => {
    switch (status) {
      case 'completed':
        return '✅';
      case 'running':
        return '⏳';
      case 'error':
        return '❌';
      default:
        return '⏸️';
    }
  };

  return (
    <div className="agent-interface">
      <div className="status-bar">
        <span className={`status-indicator ${healthStatus === '服务正常' ? 'online' : 'offline'}`}></span>
        <span className="status-text">{healthStatus}</span>
      </div>

      <form onSubmit={handleSubmit} className="agent-form">
        <div className="form-group">
          <label htmlFor="query">研究问题 *</label>
          <textarea
            id="query"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="请输入您的研究问题，例如：请基于现有论文摘要生成新的研究想法"
            rows={4}
            required
            disabled={loading}
          />
        </div>

        <div className="form-row">
          <div className="form-group">
            <label htmlFor="topic">研究主题</label>
            <input
              id="topic"
              type="text"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              placeholder="例如：agent"
              disabled={loading}
            />
          </div>

          <div className="form-group">
            <label htmlFor="methodology">研究方法</label>
            <input
              id="methodology"
              type="text"
              value={methodology}
              onChange={(e) => setMethodology(e.target.value)}
              placeholder="例如：LLM, Agent, Tool, Memory"
              disabled={loading}
            />
          </div>
        </div>

        <div className="button-group">
          <button 
            type="submit" 
            className="submit-button"
            disabled={loading || healthStatus !== '服务正常'}
          >
            {loading ? (
              <>
                <span className="spinner"></span>
                处理中...
              </>
            ) : (
              '运行 AI Agent'
            )}
          </button>
          
          {loading && streamAbortController && (
            <button
              type="button"
              className="cancel-button"
              onClick={handleCancel}
            >
              取消
            </button>
          )}
        </div>
      </form>

      {/* 工作流进度显示 */}
      {workflowSteps.length > 0 && (
        <div className="workflow-progress">
          <h3>工作流进度</h3>
          <div className="steps-container">
            {workflowSteps.map((step, index) => (
              <div
                key={step.id}
                className={`workflow-step ${step.status} ${
                  currentStep === step.id ? 'current' : ''
                }`}
              >
                <div className="step-header">
                  <span className="step-icon">{getStepStatusIcon(step.status)}</span>
                  <span className="step-name">{step.name}</span>
                </div>
                <div className="step-status">{step.status}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 工作流日志显示 */}
      {workflowLogs.length > 0 && (
        <WorkflowLogs logs={workflowLogs} />
      )}

      {error && (
        <div className="error-message">
          <strong>错误：</strong>{error}
        </div>
      )}

      {response && (
        <div className="response-container">
          {response.success ? (
            <div className="response-success">
              <h3>处理结果</h3>
              
              {response.data?.new_idea && (
                <div className="result-section">
                  <h4>新想法</h4>
                  <p>{response.data.new_idea}</p>
                </div>
              )}

              {response.data?.motivation && (
                <div className="result-section">
                  <h4>研究动机</h4>
                  <p>{response.data.motivation}</p>
                </div>
              )}

              {response.data?.summary && (
                <div className="result-section">
                  <h4>摘要</h4>
                  <p>{response.data.summary}</p>
                </div>
              )}

              {response.data?.results && (
                <div className="result-section">
                  <h4>研究结果</h4>
                  <p>{response.data.results}</p>
                </div>
              )}

              {response.data?.latex_revision && (
                <div className="result-section">
                  <h4>LaTeX 文档</h4>
                  <pre className="latex-content">{response.data.latex_revision}</pre>
                </div>
              )}
            </div>
          ) : (
            <div className="response-error">
              <strong>处理失败：</strong>{response.error}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default AgentInterface;
