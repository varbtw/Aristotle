// Aristotle - Clean UI JavaScript

// API Configuration
const API_BASE_URL = 'http://localhost:8000';

document.addEventListener('DOMContentLoaded', function() {
    const searchInput = document.getElementById('searchInput');
    const submitBtn = document.getElementById('submitBtn');
    const resultsContainer = document.getElementById('results');

    // Focus search input on page load
    searchInput.focus();

    // Handle search submission
    async function handleSearch() {
        const query = searchInput.value.trim();
        
        if (!query) {
            return;
        }

        // Show loading state
        resultsContainer.classList.remove('show');
        resultsContainer.innerHTML = '<div class="result-item"><div class="result-text"><div class="loading" style="display: inline-block;"></div> <span style="margin-left: 10px;">Processing...</span></div></div>';
        resultsContainer.classList.add('show');
        
        try {
            // Call FastAPI backend
            const response = await fetch(`${API_BASE_URL}/query`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ query: query })
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            displayResults(data.response, query);
        } catch (error) {
            console.error('Error:', error);
            // Fallback to mock results if API is not available
            displayMockResults(query);
        }
    }

    // Display real results from API
    function displayResults(response, query) {
        // Check if it's a command to determine formatting
        const isCommand = query.startsWith('/');
        
        let resultHTML = '';
        
        if (isCommand) {
            // Format command responses
            const parts = query.split(' ');
            const command = parts[0].toLowerCase();
            
            // Create formatted result based on command type
            switch(command) {
                case '/search':
                    resultHTML = formatSearchResults(response, parts.slice(1).join(' '));
                    break;
                case '/sum':
                    resultHTML = formatSummaryResults(response, parts.slice(1).join(' '));
                    break;
                case '/fact':
                    resultHTML = formatFactCheckResults(response);
                    break;
                case '/factpaper':
                    resultHTML = formatFactPaperResults(response);
                    break;
                case '/audit':
                    resultHTML = formatAuditResults(response);
                    break;
                case '/niche':
                    resultHTML = formatNicheResults(response, parts.slice(1).join(' '));
                    break;
                default:
                    resultHTML = formatGenericResult(response);
            }
        } else {
            // Regular query result
            resultHTML = formatGenericResult(response);
        }

        resultsContainer.innerHTML = resultHTML;
        resultsContainer.classList.add('show');
    }

    // Format functions for different result types
    function formatSearchResults(response, query) {
        // Split into papers by double newline or numbered items
        const papers = response.split(/\n(?=\d+\.\s)/).filter(p => p.trim());
        
        let formattedPapers = papers.map((paper, idx) => {
            const lines = paper.split('\n');
            let html = '';
            
            lines.forEach(line => {
                const trimmed = line.trim();
                const originalLine = line;
                
                if (!trimmed) {
                    html += '<br>';
                    return;
                }
                
                // Check if it's a title line (starts with number)
                if (/^\d+\.\s/.test(trimmed)) {
                    const content = trimmed.replace(/^\d+\.\s/, '');
                    html += `<div style="margin-bottom: 0.5rem;"><strong style="color: var(--accent);">${idx + 1}.</strong> ${content}</div>`;
                }
                // Check if it's indented (3 spaces = URL or other info)
                else if (originalLine.startsWith('   ')) {
                    const content = trimmed;
                    // Check if it's a URL
                    if (/^https?:\/\//.test(content)) {
                        html += `<div style="margin: 0.5rem 0;"><a href="${content}" target="_blank" style="color: var(--accent); word-break: break-all; text-decoration: none;">${content}</a></div>`;
                    }
                    // Check if it's authors line
                    else if (content.startsWith('Authors:')) {
                        html += `<div style="color: var(--text-secondary); margin: 0.25rem 0; padding-left: 1rem; font-style: italic;">${content}</div>`;
                    }
                    // Otherwise it's a description
                    else {
                        html += `<div style="color: var(--text-secondary); margin: 0.5rem 0; padding-left: 1rem; line-height: 1.5;">${content}</div>`;
                    }
                }
                // Fallback for other URLs
                else if (/^https?:\/\//.test(trimmed)) {
                    html += `<div style="margin: 0.5rem 0;"><a href="${trimmed}" target="_blank" style="color: var(--accent); word-break: break-all; text-decoration: none;">${trimmed}</a></div>`;
                }
                else {
                    html += `<div style="margin: 0.5rem 0;">${trimmed}</div>`;
                }
            });
            
            return `<div style="margin-bottom: 2rem; padding-bottom: 1.5rem; border-bottom: 1px solid var(--border-color);">${html}</div>`;
        }).join('');
        
        return `
            <div class="result-item">
                <h3 class="result-title">Search Results for: "${query}"</h3>
                <div class="result-text" style="margin-top: 1rem;">${formattedPapers}</div>
            </div>
        `;
    }

    function formatSummaryResults(response, query) {
        // Split into main content and citations
        const citationsMatch = response.match(/\n\nCitations:\n(.*)/s);
        let mainContent = response;
        let citations = '';
        
        if (citationsMatch) {
            mainContent = response.substring(0, response.indexOf('\n\nCitations:'));
            citations = citationsMatch[1];
        }
        
        // Format main content with tighter spacing
        let formatted = mainContent
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.*?)\*/g, '<em>$1</em>');
        
        // Convert bullet lists
        formatted = formatted.replace(/^\*\s(.+)$/gm, '<li>$1</li>');
        
        // Split into sections and format
        const sections = formatted.split(/\n(?=\w)/);
        let result = [];
        let inList = false;
        let listItems = [];
        
        sections.forEach(section => {
            const lines = section.trim().split('\n');
            
            lines.forEach(line => {
                if (line.trim().match(/^<li/)) {
                    if (!inList) {
                        inList = true;
                        listItems = [];
                    }
                    listItems.push(line);
                } else {
                    if (inList && listItems.length > 0) {
                        result.push(`<ul style="margin: 0.5rem 0; padding-left: 1.5rem; list-style-type: disc;">${listItems.join('')}</ul>`);
                        inList = false;
                        listItems = [];
                    }
                    
                    const trimmed = line.trim();
                    if (trimmed) {
                        // Check if it's a section header (ends with :)
                        if (trimmed.endsWith(':')) {
                            result.push(`<h4 style="margin: 1rem 0 0.5rem 0; font-weight: 600; color: var(--text-primary);">${trimmed}</h4>`);
                        } else if (!trimmed.startsWith('<')) {
                            result.push(`<p style="margin: 0.5rem 0;">${trimmed}</p>`);
                        } else {
                            result.push(trimmed);
                        }
                    }
                }
            });
        });
        
        // Close any remaining list
        if (inList && listItems.length > 0) {
            result.push(`<ul style="margin: 0.5rem 0; padding-left: 1.5rem; list-style-type: disc;">${listItems.join('')}</ul>`);
        }
        
        // Format citations if present
        let citationsHTML = '';
        if (citations) {
            const citationLines = citations.trim().split('\n');
            citationsHTML = '<div style="margin-top: 1.5rem; padding-top: 1rem; border-top: 1px solid var(--border-color);">';
            citationsHTML += '<strong style="color: var(--text-primary); font-size: 1rem; display: block; margin-bottom: 0.75rem;">Citations:</strong>';
            
            citationLines.forEach((line, idx) => {
                const trimmed = line.trim();
                if (!trimmed) return;
                
                // Parse citation format
                const urlMatch = trimmed.match(/(https?:\/\/[^\s]+)/);
                if (urlMatch) {
                    const url = urlMatch[1];
                    const rest = trimmed.replace(url, '').trim();
                    const isNumbered = /^\d+\.\s/.test(rest);
                    
                    citationsHTML += `<div style="margin: 0.5rem 0; padding-left: ${isNumbered ? '0' : '1rem'};"><a href="${url}" target="_blank" style="color: var(--accent); word-break: break-all; text-decoration: none;">${rest}</a></div>`;
                } else {
                    citationsHTML += `<div style="margin: 0.5rem 0; padding-left: 1rem;">${trimmed}</div>`;
                }
            });
            citationsHTML += '</div>';
        }
        
        return `
            <div class="result-item">
                <h3 class="result-title">Summary: ${query}</h3>
                <div class="result-text" style="margin-top: 1rem; line-height: 1.6;">${result.join('')}${citationsHTML}</div>
            </div>
        `;
    }

    function formatFactCheckResults(response) {
        // Parse the structured fact-check response
        const verdictMatch = response.match(/Verdict:\s*(.+)/);
        const confidenceMatch = response.match(/Confidence:\s*(.+)/);
        const rationaleMatch = response.match(/Rationale:\s*(.+?)(?=\nCitations:|$)/s);
        const citationsMatch = response.match(/Citations:\n(.*)/s);
        
        let html = '';
        
        // Format Verdict
        if (verdictMatch) {
            const verdict = verdictMatch[1].trim();
            let color = 'var(--text-secondary)';
            if (verdict.toLowerCase().includes('supported')) {
                color = '#4ade80';
            } else if (verdict.toLowerCase().includes('contradicted')) {
                color = '#f87171';
            } else if (verdict.toLowerCase().includes('insufficient')) {
                color = '#fbbf24';
            }
            html += `<div style="margin: 0.5rem 0;"><strong>Verdict:</strong> <span style="color: ${color};">${verdict}</span></div>`;
        }
        
        // Format Confidence
        if (confidenceMatch) {
            const confidence = confidenceMatch[1].trim();
            html += `<div style="margin: 0.5rem 0;"><strong>Confidence:</strong> ${confidence}</div>`;
        }
        
        // Format Rationale
        if (rationaleMatch) {
            const rationale = rationaleMatch[1].trim();
            html += `<div style="margin: 1rem 0;"><strong>Rationale:</strong></div>`;
            html += `<div style="margin: 0.5rem 0; line-height: 1.6; color: var(--text-secondary);">${rationale}</div>`;
        }
        
        // Format Citations
        if (citationsMatch) {
            const citations = citationsMatch[1].trim();
            html += `<div style="margin-top: 1.5rem; padding-top: 1rem; border-top: 1px solid var(--border-color);">`;
            html += `<strong style="color: var(--text-primary); font-size: 1rem; display: block; margin-bottom: 0.75rem;">Citations:</strong>`;
            
            const citationLines = citations.split('\n').filter(line => line.trim());
            citationLines.forEach(line => {
                const trimmed = line.trim();
                if (!trimmed) return;
                
                // Parse citation format: 1) Title (Year) — URL
                const match = trimmed.match(/^\d+\)\s(.+?)\s\((.+?)\)\s—\s(https?:\/\/[^\s]+)/);
                if (match) {
                    const [, title, year, url] = match;
                    html += `<div style="margin: 0.5rem 0;"><strong>${title}</strong> (${year}) — <a href="${url}" target="_blank" style="color: var(--accent); word-break: break-all; text-decoration: none;">${url}</a></div>`;
                } else {
                    const urlMatch = trimmed.match(/(https?:\/\/[^\s]+)/);
                    if (urlMatch) {
                        const url = urlMatch[1];
                        const rest = trimmed.replace(url, '').trim();
                        html += `<div style="margin: 0.5rem 0;">${rest} — <a href="${url}" target="_blank" style="color: var(--accent); word-break: break-all; text-decoration: none;">${url}</a></div>`;
                    } else {
                        html += `<div style="margin: 0.5rem 0;">${trimmed}</div>`;
                    }
                }
            });
            html += '</div>';
        }
        
        // If parsing failed, fall back to basic formatting
        if (!html) {
            html = formatResponse(response);
        }
        
        return `
            <div class="result-item">
                <h3 class="result-title">Fact Check Result</h3>
                <div class="result-text" style="margin-top: 1rem; line-height: 1.6;">${html}</div>
            </div>
        `;
    }

    function formatFactPaperResults(response) {
        return `
            <div class="result-item">
                <h3 class="result-title">Paper Analysis</h3>
                <div class="result-text">${response}</div>
            </div>
        `;
    }

    function formatAuditResults(response) {
        let formatted = response;
        
        // Try to match the formatted version first
        const statsMatch = response.match(/Database Statistics\n([\s\S]*?)\n\nDatabase Status:/);
        const statusMatch = response.match(/Database Status:\s*(.+)/);
        
        let html = '';
        
        if (statsMatch) {
            const stats = statsMatch[1].trim();
            html += '<div style="margin: 0.5rem 0;">';
            
            stats.split('\n').forEach(line => {
                const trimmed = line.trim();
                if (!trimmed) return;
                
                if (trimmed.includes('Total Papers:')) {
                    html += `<div style="margin: 0.75rem 0; font-size: 1.1rem;"><strong>${trimmed}</strong></div>`;
                } else if (trimmed.includes('With Abstracts:') || trimmed.includes('Missing Abstracts:')) {
                    const parts = trimmed.split('(');
                    html += `<div style="margin: 0.5rem 0; padding-left: 1rem;">${parts[0]}<span style="color: var(--text-secondary);">(${parts.slice(1).join('(')}</div>`;
                } else if (trimmed.includes('Year Range:')) {
                    html += `<div style="margin: 0.75rem 0; color: var(--text-secondary);">${trimmed}</div>`;
                } else {
                    html += `<div style="margin: 0.5rem 0;">${trimmed}</div>`;
                }
            });
            html += '</div>';
        }
        
        if (statusMatch) {
            const status = statusMatch[1].trim();
            const isHealthy = status.includes('✅');
            html += '<div style="margin-top: 1.5rem; padding-top: 1rem; border-top: 1px solid var(--border-color);">';
            html += `<div style="font-weight: 600; color: ${isHealthy ? '#4ade80' : '#fbbf24'}; font-size: 1rem;">Database Status: ${status}</div>`;
            html += '</div>';
        }
        
        // If no match, format the simple version
        if (!html) {
            const lines = response.trim().split('\n');
            lines.forEach((line, index) => {
                const trimmed = line.trim();
                if (!trimmed) return;
                
                // Handle different line types
                if (trimmed.startsWith('Total:')) {
                    const count = trimmed.replace('Total:', '').trim();
                    html += `<div style="margin: 1rem 0; font-size: 1.1rem;"><strong>Total Papers: ${count}</strong></div>`;
                } else if (trimmed.startsWith('With abstracts:')) {
                    const count = trimmed.replace('With abstracts:', '').trim();
                    html += `<div style="margin: 0.5rem 0; padding-left: 1rem;">With Abstracts: ${count}</div>`;
                } else if (trimmed.startsWith('Without abstracts:')) {
                    const count = trimmed.replace('Without abstracts:', '').trim();
                    html += `<div style="margin: 0.5rem 0; padding-left: 1rem;">Without Abstracts: ${count}</div>`;
                } else if (trimmed.startsWith('Sample missing IDs:')) {
                    const ids = trimmed.replace('Sample missing IDs:', '').trim();
                    html += '<div style="margin: 1.5rem 0; padding-top: 1rem; border-top: 1px solid var(--border-color);"><strong>Sample Missing IDs:</strong></div>';
                    html += `<div style="margin: 0.5rem 0; padding-left: 1rem; font-family: monospace; font-size: 0.9rem; color: var(--text-secondary); word-break: break-all;">${ids}</div>`;
                } else if (trimmed.startsWith('PaperId:')) {
                    html += `<div style="margin: 1rem 0; font-weight: 600; color: var(--text-primary);">${trimmed}</div>`;
                } else if (trimmed.match(/^(title|year|url|has_abstract_in_meta|document_snippet):/)) {
                    html += `<div style="margin: 0.5rem 0; padding-left: 1rem; color: var(--text-secondary);">${trimmed}</div>`;
                } else {
                    html += `<div style="margin: 0.5rem 0;">${trimmed}</div>`;
                }
            });
        }
        
        if (!html) {
            html = response.replace(/\n/g, '<br>');
        }
        
        return `
            <div class="result-item">
                <h3 class="result-title">Database Statistics</h3>
                <div class="result-text" style="margin-top: 1rem; line-height: 1.6;">${html}</div>
            </div>
        `;
    }

    function formatNicheResults(response, query) {
        // Parse the niche indexing result
        const lines = response.trim().split('\n');
        let html = '';
        
        lines.forEach(line => {
            const trimmed = line.trim();
            if (!trimmed) return;
            
            // Highlight success message
            if (trimmed.includes('successfully')) {
                html += `<div style="margin: 1rem 0; font-size: 1.1rem; color: #4ade80; font-weight: 600;">✅ ${trimmed}</div>`;
            }
            // Highlight section headers
            else if (trimmed.includes('Topic:')) {
                const topic = trimmed.replace('Topic:', '').trim();
                html += `<div style="margin: 0.75rem 0;"><strong style="color: var(--text-primary);">Topic:</strong> ${topic}</div>`;
            }
            // Highlight statistics
            else if (trimmed.includes('Total papers fetched:') || trimmed.includes('Papers with abstracts:')) {
                html += `<div style="margin: 0.5rem 0; padding-left: 1rem; color: var(--text-secondary);">${trimmed}</div>`;
            }
            // Highlight action
            else if (trimmed.includes('Papers indexed')) {
                html += `<div style="margin: 0.75rem 0; color: var(--accent);">📚 ${trimmed}</div>`;
            }
            // Default formatting
            else {
                html += `<div style="margin: 0.5rem 0;">${trimmed}</div>`;
            }
        });
        
        return `
            <div class="result-item">
                <h3 class="result-title">Niche Papers Indexing: "${query}"</h3>
                <div class="result-text" style="margin-top: 1rem; line-height: 1.6;">${html}</div>
            </div>
        `;
    }

    function formatGenericResult(response) {
        return `
            <div class="result-item">
                <div class="result-text">${formatResponse(response)}</div>
            </div>
        `;
    }

    function formatResponse(text) {
        let formatted = text
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.*?)\*/g, '<em>$1</em>');
        
        formatted = formatted.replace(/^(\d+)\.\s(.+)$/gm, '<li style="margin: 0.5rem 0;">$2</li>');
        formatted = formatted.replace(/^[-•]\s(.+)$/gm, '<li style="margin: 0.5rem 0;">$1</li>');
        formatted = formatted.replace(/^\*\s(.+)$/gm, '<li style="margin: 0.5rem 0;">$1</li>');
        
        const lines = formatted.split('\n');
        let result = [];
        let inList = false;
        let listItems = [];
        
        lines.forEach((line, index) => {
            const trimmed = line.trim();
            
            if (trimmed.match(/^<li/)) {
                if (!inList) {
                    inList = true;
                    listItems = [];
                }
                listItems.push(trimmed);
            } else {
                if (inList && listItems.length > 0) {
                    result.push(`<ul style="margin: 1rem 0; padding-left: 1.5rem; list-style-type: disc;">${listItems.join('')}</ul>`);
                    inList = false;
                    listItems = [];
                }
                
                if (trimmed) {
                    result.push(`<p style="margin: 1rem 0;">${trimmed}</p>`);
                } else if (index === lines.length - 1) {
                } else {
                    result.push('<br>');
                }
            }
        });
        
        if (inList && listItems.length > 0) {
            result.push(`<ul style="margin: 1rem 0; padding-left: 1.5rem; list-style-type: disc;">${listItems.join('')}</ul>`);
        }
        
        return result.join('');
    }

    // Mock results as fallback
    function displayMockResults(query) {
        let resultHTML = '';
        
        if (query.startsWith('/')) {
            const parts = query.split(' ');
            const command = parts[0].toLowerCase();
            
            switch(command) {
                case '/search':
                    resultHTML = createMockSearchResults(parts.slice(1).join(' '));
                    break;
                case '/sum':
                    resultHTML = createMockSummaryResults(parts.slice(1).join(' '));
                    break;
                case '/fact':
                    resultHTML = createMockFactCheckResults(parts.slice(1).join(' '));
                    break;
                case '/factpaper':
                    resultHTML = createMockFactPaperResults(parts[1] || '');
                    break;
                case '/audit':
                    resultHTML = createMockAuditResults();
                    break;
                case '/niche':
                    resultHTML = createMockNicheResults(parts.slice(1).join(' '));
                    break;
                default:
                    resultHTML = createMockGeneralResponse(query);
            }
        } else {
            resultHTML = createMockGeneralResponse(query);
        }

        resultsContainer.innerHTML = resultHTML;
        resultsContainer.classList.add('show');
    }

    function createMockSearchResults(query) {
        return `
            <div class="result-item">
                <h3 class="result-title">Search Results for: "${query}"</h3>
                <div class="result-text">
                    <p>Found 15 relevant papers in the database.</p>
                    <br>
                    <strong>Sample Papers:</strong>
                    <ul style="margin-top: 0.5rem; padding-left: 1.5rem; color: var(--text-secondary);">
                        <li>"Machine Learning Applications in Healthcare" (2024)</li>
                        <li>"The Impact of AI on Modern Medical Diagnosis" (2023)</li>
                    </ul>
                </div>
            </div>
        `;
    }

    function createMockSummaryResults(query) {
        return `
            <div class="result-item">
                <h3 class="result-title">Summary: ${query}</h3>
                <div class="result-text">
                    <p><strong>Key Findings:</strong></p>
                    <ul style="margin-top: 0.5rem; padding-left: 1.5rem; color: var(--text-secondary);">
                        <li>Recent studies show significant improvements in accuracy using deep learning models.</li>
                        <li>Healthcare AI adoption has increased by 45% in the past two years.</li>
                    </ul>
                </div>
            </div>
        `;
    }

    function createMockFactCheckResults(claim) {
        return `
            <div class="result-item">
                <h3 class="result-title">Fact Check: "${claim}"</h3>
                <div class="result-text">
                    <p><strong>Verdict:</strong> <span style="color: #4ade80;">Supported</span></p>
                    <p><strong>Confidence:</strong> 85%</p>
                </div>
            </div>
        `;
    }

    function createMockFactPaperResults(paperId) {
        return `
            <div class="result-item">
                <h3 class="result-title">Paper Analysis: ${paperId || 'Sample Paper'}</h3>
                <div class="result-text">Analysis would appear here</div>
            </div>
        `;
    }

    function createMockAuditResults() {
        return `
            <div class="result-item">
                <h3 class="result-title">Database Audit Results</h3>
                <div class="result-text">
                    <p style="margin-bottom: 1rem;"><strong>Total Papers:</strong> 1,247</p>
                    <p style="margin-bottom: 1rem;"><strong>With Abstracts:</strong> 1,089 (87.3%)</p>
                </div>
            </div>
        `;
    }

    function createMockNicheResults(query) {
        return `
            <div class="result-item">
                <h3 class="result-title">Niche Papers Indexing: "${query}"</h3>
                <div class="result-text">
                    <p style="color: #4ade80; font-weight: 600;">✅ Niche papers indexed successfully!</p>
                    <p style="margin-top: 1rem;"><strong>Topic:</strong> ${query}</p>
                    <p style="padding-left: 1rem; color: var(--text-secondary);">Total papers fetched: 100</p>
                    <p style="padding-left: 1rem; color: var(--text-secondary);">Papers with abstracts: 85 (85.0%)</p>
                    <p style="margin-top: 1rem; color: var(--accent);">📚 Papers indexed to ChromaDB</p>
                </div>
            </div>
        `;
    }

    function createMockGeneralResponse(query) {
        return `
            <div class="result-item">
                <h3 class="result-title">Searching for: "${query}"</h3>
                <div class="result-text">
                    <p>This is a mock response. The API backend is not available.</p>
                </div>
            </div>
        `;
    }

    // Event listeners
    submitBtn.addEventListener('click', handleSearch);

    searchInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            handleSearch();
        }
    });

    // Add click handlers to command items
    document.querySelectorAll('.command-item').forEach(item => {
        item.addEventListener('click', function() {
            const command = this.getAttribute('data-command');
            if (command) {
                searchInput.value = command;
                searchInput.focus();
            }
        });
    });
});

