// Research Agent - JavaScript for live feedback

const API_BASE_URL = 'http://localhost:8000';

document.addEventListener('DOMContentLoaded', function() {
    const topicInput = document.getElementById('topicInput');
    const startResearchBtn = document.getElementById('startResearchBtn');
    const feedbackContainer = document.getElementById('feedbackContainer');
    const feedbackContent = document.getElementById('feedbackContent');
    const resultsContainer = document.getElementById('resultsContainer');
    const progressFill = document.getElementById('progressFill');

    // Focus topic input on page load
    topicInput.focus();

    // Progress tracking
    let progress = 0;
    const stages = [
        'Initializing...',
        'Conducting literature review...',
        'Fetching papers...',
        'Analyzing literature...',
        'Generating hypotheses...',
        'Creating simulations...',
        'Writing paper...',
        'Finalizing...'
    ];

    async function startResearch() {
        const topic = topicInput.value.trim();
        
        if (!topic) {
            alert('Please enter a research topic');
            return;
        }

        // Disable input and button during research
        topicInput.disabled = true;
        startResearchBtn.disabled = true;
        startResearchBtn.textContent = 'Processing...';

        // Show feedback container
        feedbackContainer.style.display = 'block';
        feedbackContent.innerHTML = '';
        progress = 0;
        updateProgress(10);

        try {
            // Call the research agent API
            const response = await fetch(`${API_BASE_URL}/research`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ topic: topic })
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            // Handle streaming response
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop(); // Keep incomplete line in buffer

                for (const line of lines) {
                    if (line.trim()) {
                        handleStreamLine(line.trim());
                    }
                }
            }

            // Process any remaining buffer
            if (buffer.trim()) {
                handleStreamLine(buffer.trim());
            }

        } catch (error) {
            console.error('Error:', error);
            addFeedback('Error: ' + error.message, 'error');
            topicInput.disabled = false;
            startResearchBtn.disabled = false;
            startResearchBtn.textContent = 'Generate Paper';
        }
    }

    function handleStreamLine(line) {
        try {
            // Handle SSE format: "data: {json}"
            if (line.startsWith('data: ')) {
                line = line.substring(6); // Remove "data: " prefix
            }
            const data = JSON.parse(line);
            
            if (data.type === 'progress') {
                updateProgress(data.percent || 0);
            }
            
            if (data.type === 'stage') {
                addFeedback(data.message || '', 'stage');
                if (data.percent) {
                    updateProgress(data.percent);
                }
            }
            
            if (data.type === 'info') {
                addFeedback(data.message || '', 'info');
            }
            
            if (data.type === 'complete') {
                displayResults(data.result || {});
                progress = 100;
                updateProgress(100);
                
                // Re-enable input and button
                topicInput.disabled = false;
                startResearchBtn.disabled = false;
                startResearchBtn.textContent = 'Generate Paper';
            }
        } catch (e) {
            // Not JSON, just display as info
            if (line.startsWith('[INFO]') || line.startsWith('[WARNING]')) {
                addFeedback(line, 'info');
            }
        }
    }

    function updateProgress(percent) {
        progress = Math.min(100, Math.max(0, percent));
        progressFill.style.width = `${progress}%`;
    }

    function addFeedback(message, type = 'info') {
        const timestamp = new Date().toLocaleTimeString();
        const icon = getIcon(type);
        
        const feedbackItem = document.createElement('div');
        feedbackItem.className = `feedback-item feedback-${type}`;
        feedbackItem.innerHTML = `
            <span class="feedback-icon">${icon}</span>
            <span class="feedback-message">${escapeHtml(message)}</span>
            <span class="feedback-time">${timestamp}</span>
        `;
        
        feedbackContent.appendChild(feedbackItem);
        feedbackContent.scrollTop = feedbackContent.scrollHeight;
    }

    function getIcon(type) {
        switch(type) {
            case 'stage': return '⏳';
            case 'info': return 'ℹ️';
            case 'success': return '✅';
            case 'error': return '❌';
            case 'warning': return '⚠️';
            default: return '•';
        }
    }

    function displayResults(data) {
        resultsContainer.style.display = 'block';
        
        let html = `
            <div class="result-item">
                <h3 class="result-title">Research Complete! 🎉</h3>
                <div class="result-text" style="margin-top: 1rem;">
        `;
        
        if (data.output_path) {
            html += `
                    <div style="margin-bottom: 1rem;">
                        <strong>Output Location:</strong> <code>${data.output_path}</code>
                    </div>
            `;
        }
        
        if (data.papers_analyzed) {
            html += `
                    <div style="margin-bottom: 0.5rem;">
                        <strong>Papers Analyzed:</strong> ${data.papers_analyzed}
                    </div>
            `;
        }
        
        if (data.hypotheses_generated) {
            html += `
                    <div style="margin-bottom: 0.5rem;">
                        <strong>Hypotheses Generated:</strong> ${data.hypotheses_generated}
                    </div>
            `;
        }
        
        if (data.simulations_created) {
            html += `
                    <div style="margin-bottom: 1rem;">
                        <strong>Simulations Created:</strong> ${data.simulations_created}
                    </div>
            `;
        }
        
        html += `
                    <div style="padding: 1rem; background: var(--bg-tertiary); border-radius: 8px; margin-top: 1rem;">
                        <p><strong>Generated Files:</strong></p>
                        <ul style="margin: 0.5rem 0; padding-left: 1.5rem;">
                            <li>paper.md - Complete research paper</li>
                            <li>literature_analysis.json - Literature review data</li>
                            <li>hypotheses.json - Generated hypotheses</li>
                            <li>simulations/*.py - Python simulation scripts</li>
                            <li>metadata.json - Research metadata</li>
                        </ul>
                    </div>
                </div>
            </div>
        `;
        
        resultsContainer.innerHTML = html;
        resultsContainer.scrollIntoView({ behavior: 'smooth' });
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // Event listeners
    startResearchBtn.addEventListener('click', startResearch);

    topicInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            startResearch();
        }
    });
});

