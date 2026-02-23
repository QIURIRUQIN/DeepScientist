import React, { useState } from 'react';
import './App.css';
import AgentInterface from './components/AgentInterface';

const App: React.FC = () => {
  return (
    <div className="App">
      <header className="App-header">
        <h1>DeepScientist AI Agent</h1>
        <p>智能科研助手 - 基于AI的自动化研究工具</p>
      </header>
      <main className="App-main">
        <AgentInterface />
      </main>
    </div>
  );
};

export default App;
