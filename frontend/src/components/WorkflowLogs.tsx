import React from 'react';
import './WorkflowLogs.css';

export interface LogEntry {
  step: string;
  timestamp: string;
  message: string;
  data?: any;
}

interface WorkflowLogsProps {
  logs: LogEntry[];
}

const WorkflowLogs: React.FC<WorkflowLogsProps> = ({ logs }) => {
  if (logs.length === 0) {
    return null;
  }

  const formatPaperUrl = (url: string): string => {
    // 提取arxiv ID
    if (url.includes('arxiv.org')) {
      const match = url.match(/arxiv\.org\/pdf\/([\d.]+v?\d*)/);
      if (match) {
        return match[1];
      }
    }
    return url;
  };

  const renderLogContent = (log: LogEntry) => {
    const { step, data } = log;

    // 文献搜索阶段
    if (step === 'literature_search' && data) {
      return (
        <div className="log-details">
          {data.paper_urls && data.paper_urls.length > 0 && (
            <div className="log-section">
              <h4>📄 找到的论文 ({data.paper_urls.length} 篇)</h4>
              <ul className="paper-list">
                {data.paper_urls.map((url: string, idx: number) => (
                  <li key={idx} className="paper-item">
                    <a href={url} target="_blank" rel="noopener noreferrer" className="paper-link">
                      {formatPaperUrl(url)}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {data.downloaded_papers && data.downloaded_papers.length > 0 && (
            <div className="log-section">
              <h4>💾 已下载的论文 ({data.downloaded_papers.length} 篇)</h4>
              <ul className="paper-list">
                {data.downloaded_papers.map((path: string, idx: number) => (
                  <li key={idx} className="paper-item">
                    <span className="paper-path">{path.split('/').pop()}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {data.refined_query && (
            <div className="log-section">
              <h4>🔍 优化后的查询</h4>
              <p className="query-text">{data.refined_query}</p>
            </div>
          )}
        </div>
      );
    }

    // 文献解析阶段
    if (step === 'literature_parser' && data) {
      return (
        <div className="log-details">
          {data.parsed_papers && data.parsed_papers.length > 0 && (
            <div className="log-section">
              <h4>📚 解析结果</h4>
              <div className="parsed-papers">
                {data.parsed_papers.map((paper: any, idx: number) => (
                  <div key={idx} className={`parsed-paper ${paper.status}`}>
                    <div className="paper-header">
                      <span className="paper-name">{paper.pdf_path?.split('/').pop() || `论文 ${idx + 1}`}</span>
                      <span className={`status-badge ${paper.status}`}>
                        {paper.status === 'success' ? '✅' : '❌'} {paper.status}
                      </span>
                    </div>
                    {paper.status === 'success' && (
                      <div className="paper-stats">
                        <span>📊 图表: {paper.figures_count} 个</span>
                      </div>
                    )}
                  </div>
                ))}
              </div>
              {data.parsed_count !== undefined && (
                <div className="summary-stats">
                  成功解析: {data.parsed_count} / {data.total_papers || data.parsed_papers.length}
                </div>
              )}
            </div>
          )}
        </div>
      );
    }

    // AI科学家阶段
    if (step === 'AIScientist' && data) {
      return (
        <div className="log-details">
          {data.new_idea && (
            <div className="log-section">
              <h4>💡 新想法</h4>
              <p className="idea-text">{data.new_idea}</p>
            </div>
          )}
          {data.motivation && (
            <div className="log-section">
              <h4>🎯 研究动机</h4>
              <p className="motivation-text">{data.motivation}</p>
            </div>
          )}
          {data.dataset && (
            <div className="log-section">
              <h4>📊 数据集</h4>
              <p>名称: {data.dataset}</p>
              {data.dataset_url && (
                <p>
                  链接: <a href={data.dataset_url} target="_blank" rel="noopener noreferrer">{data.dataset_url}</a>
                </p>
              )}
            </div>
          )}
        </div>
      );
    }

    // 数据分析阶段
    if (step === 'data_analyser' && data) {
      return (
        <div className="log-details">
          {data.column_count !== undefined && (
            <div className="log-section">
              <h4>📈 数据分析</h4>
              <p>数据列数: {data.column_count}</p>
            </div>
          )}
        </div>
      );
    }

    // 代码实验阶段
    if (step === 'code_experiment' && data) {
      return (
        <div className="log-details">
          <div className="log-section">
            <h4>💻 代码实验</h4>
            <div className="experiment-stats">
              <span>迭代次数: {data.iteration_count || 0}</span>
              <span>质量分数: {(data.quality_score || 0).toFixed(2)}</span>
              <span>执行状态: {data.execution_success ? '✅ 成功' : '⏳ 进行中'}</span>
              {data.output_figures_count !== undefined && (
                <span>生成图表: {data.output_figures_count} 个</span>
              )}
            </div>
          </div>
        </div>
      );
    }

    // LaTeX写作阶段
    if (step === 'latex_writer' && data) {
      return (
        <div className="log-details">
          <div className="log-section">
            <h4>📝 LaTeX文档</h4>
            <p>修订次数: {data.revision_count || 0}</p>
            {data.latex_revision && (
              <div className="latex-preview">
                <pre>{data.latex_revision}</pre>
              </div>
            )}
          </div>
        </div>
      );
    }

    // 默认显示消息
    if (data?.message) {
      return <div className="log-message">{data.message}</div>;
    }

    return null;
  };

  return (
    <div className="workflow-logs">
      <h3>📋 工作流日志</h3>
      <div className="logs-container">
        {logs.map((log, idx) => (
          <div key={idx} className={`log-entry log-${log.step}`}>
            <div className="log-header">
              <span className="log-step">{log.step}</span>
              <span className="log-time">{log.timestamp}</span>
            </div>
            {renderLogContent(log)}
          </div>
        ))}
      </div>
    </div>
  );
};

export default WorkflowLogs;
