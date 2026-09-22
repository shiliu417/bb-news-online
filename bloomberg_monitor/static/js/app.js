document.addEventListener("DOMContentLoaded", () => {
    // App State
    let currentPage = 1;
    let totalPages = 1;
    let currentCategory = "";
    let currentSearch = "";
    let currentSentiment = "";
    let showEnglish = true;
    let chinaOnly = true;
    let currentArticleId = null;
    let pollInterval = null;

    let autoRefreshEnabled = false;
    let autoRefreshTimer = null;
    let autoRefreshCountdown = 60;

    // Elements
    const newsGrid = document.getElementById("news-grid");
    const categoryTabs = document.getElementById("category-tabs");
    const searchInput = document.getElementById("search-input");
    const clearSearchBtn = document.getElementById("btn-clear-search");
    const filterSentiment = document.getElementById("filter-sentiment");
    const toggleEnglish = document.getElementById("toggle-english");
    const toggleChinaOnly = document.getElementById("toggle-china-only");
    
    const btnTriggerScrape = document.getElementById("btn-trigger-scrape");
    const btnAutoRefresh = document.getElementById("btn-auto-refresh");
    const autoRefreshLabel = document.getElementById("auto-refresh-label");
    const btnSettings = document.getElementById("btn-settings");
    const btnMobile = document.getElementById("btn-mobile");
    const scrapeBanner = document.getElementById("scrape-progress-banner");

    const statTotal = document.getElementById("stat-total");
    const statChina = document.getElementById("stat-china");
    const statTime = document.getElementById("stat-time");
    const sentBull = document.getElementById("sent-bull-count");
    const sentNeutral = document.getElementById("sent-neutral-count");
    const sentBear = document.getElementById("sent-bear-count");

    const paginationBar = document.getElementById("pagination-bar");
    const btnPrevPage = document.getElementById("btn-prev-page");
    const btnNextPage = document.getElementById("btn-next-page");
    const pageIndicator = document.getElementById("page-indicator");

    // Modal Elements
    const articleModal = document.getElementById("article-modal");
    const modalClose = document.getElementById("modal-close");
    const btnFetchFullText = document.getElementById("btn-fetch-full-text");
    const btnCopyModal = document.getElementById("btn-copy-modal");

    const mobileModal = document.getElementById("mobile-modal");
    const mobileClose = document.getElementById("mobile-close");
    const mobileUrlLink = document.getElementById("mobile-url-link");
    const mobileRssLink = document.getElementById("mobile-rss-link");
    const qrImg = document.getElementById("qr-img");

    const settingsModal = document.getElementById("settings-modal");
    const settingsClose = document.getElementById("settings-close");
    const btnSaveSettings = document.getElementById("btn-save-settings");

    // Toast Utility
    function showToast(msg, duration = 3000) {
        const toast = document.getElementById("toast");
        toast.textContent = msg;
        toast.style.display = "block";
        setTimeout(() => {
            toast.style.display = "none";
        }, duration);
    }

    // Copy to clipboard helper
    function copyTextToClipboard(text, successMsg = "已复制到剪贴板") {
        if (navigator.clipboard && window.isSecureContext) {
            navigator.clipboard.writeText(text).then(() => showToast(successMsg));
        } else {
            const ta = document.createElement("textarea");
            ta.value = text;
            ta.style.position = "fixed";
            ta.style.left = "-9999px";
            document.body.appendChild(ta);
            ta.focus();
            ta.select();
            try {
                document.execCommand('copy');
                showToast(successMsg);
            } catch (err) {
                showToast("复制失败，请手动选取");
            }
            document.body.removeChild(ta);
        }
    }

    // Load Stats & Sentiment Distribution
    async function loadStats() {
        try {
            const res = await fetch("/api/stats");
            const data = await res.json();
            statTotal.textContent = data.total || 0;
            statChina.textContent = data.china_total || 0;
            
            // Sentiment Breakdown
            const sents = data.sentiments || {};
            sentBull.textContent = `🟢 ${sents["利多"] || 0}`;
            sentNeutral.textContent = `⚪ ${sents["中性"] || 0}`;
            sentBear.textContent = `🔴 ${sents["利空"] || 0}`;

            // Category Counts
            const cats = data.categories || {};
            document.getElementById("count-all").textContent = data.total || 0;
            document.getElementById("count-macro").textContent = cats["宏观政策"] || 0;
            document.getElementById("count-trade").textContent = cats["贸易关税"] || 0;
            document.getElementById("count-tech").textContent = cats["科技半导体"] || 0;
            document.getElementById("count-finance").textContent = cats["金融外汇"] || 0;
            document.getElementById("count-property").textContent = cats["房产消费"] || 0;
            document.getElementById("count-commodity").textContent = cats["大宗商品"] || 0;

            if (data.last_scraped && data.last_scraped !== "尚未抓取") {
                const dt = new Date(data.last_scraped);
                statTime.textContent = dt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
            } else {
                statTime.textContent = data.last_scraped;
            }

            if (data.is_scraping) {
                scrapeBanner.style.display = "flex";
            }
        } catch (e) {
            console.error("Failed to load stats", e);
        }
    }

    // Load News Feed
    async function loadNews() {
        newsGrid.innerHTML = `
            <div class="loading-placeholder">
                <div class="spinner"></div>
                <p>正在载入实时财经数据...</p>
            </div>
        `;

        const params = new URLSearchParams({
            page: currentPage,
            per_page: 15,
            category: currentCategory,
            sentiment: currentSentiment,
            search: currentSearch,
            china_only: chinaOnly
        });

        try {
            const res = await fetch(`/api/news?${params.toString()}`);
            const data = await res.json();
            
            if (!data.articles || data.articles.length === 0) {
                newsGrid.innerHTML = `
                    <div class="loading-placeholder">
                        <i class="fa-regular fa-folder-open" style="font-size: 2.5rem; color: var(--text-muted);"></i>
                        <p>暂无符合筛选条件的新闻报道。可点击顶部“立即抓取最新”从辛迪加源同步。</p>
                    </div>
                `;
                paginationBar.style.display = "none";
                return;
            }

            totalPages = data.total_pages || 1;
            renderArticles(data.articles);
            updatePagination();
        } catch (e) {
            newsGrid.innerHTML = `
                <div class="loading-placeholder">
                    <p style="color: var(--bb-red);">载入新闻失败，请检查网络服务连接。</p>
                </div>
            `;
        }
    }

    // Render News Cards
    function renderArticles(articles) {
        newsGrid.innerHTML = "";
        articles.forEach(article => {
            const card = document.createElement("div");
            card.className = "news-card";

            const sentimentClass = article.sentiment === "利多" ? "bullish" : (article.sentiment === "利空" ? "bearish" : "neutral");
            const sentimentEmoji = article.sentiment === "利多" ? "🟢 利多" : (article.sentiment === "利空" ? "🔴 利空" : "⚪ 中性");

            let keyPointsHtml = "";
            if (article.key_points && Array.isArray(article.key_points) && article.key_points.length > 0) {
                const items = article.key_points.slice(0, 3).map(pt => `<li><i class="fa-solid fa-angle-right" style="color:var(--bb-orange);font-size:0.7rem;"></i> ${escapeHtml(pt)}</li>`).join("");
                keyPointsHtml = `<ul class="key-points-list">${items}</ul>`;
            }

            card.innerHTML = `
                <div class="card-header">
                    <span class="tag-badge">${escapeHtml(article.category || '宏观政策')}</span>
                    <span class="sentiment-pill ${sentimentClass}">${sentimentEmoji}</span>
                </div>
                <h3 class="card-title-zh" data-id="${article.id}">${escapeHtml(article.title_zh || article.title_en)}</h3>
                ${showEnglish ? `<div class="card-title-en">${escapeHtml(article.title_en)}</div>` : ''}
                ${keyPointsHtml}
                <div class="card-summary">${escapeHtml(article.summary_zh || article.title_zh)}</div>
                <div class="card-footer">
                    <div class="source-info">
                        <span class="source-pill">${escapeHtml(article.source_name || 'Bloomberg')}</span>
                        <span>${formatDate(article.published_at)}</span>
                    </div>
                    <div class="card-actions">
                        <button class="btn-card-action btn-copy-card" title="复制摘要"><i class="fa-regular fa-copy"></i></button>
                        <button class="btn-read-more" data-id="${article.id}">详情阅读</button>
                    </div>
                </div>
            `;

            card.querySelector(".card-title-zh").addEventListener("click", () => openArticleModal(article.id));
            card.querySelector(".btn-read-more").addEventListener("click", () => openArticleModal(article.id));
            card.querySelector(".btn-copy-card").addEventListener("click", (e) => {
                e.stopPropagation();
                const shareText = `【彭博中国财经】${article.title_zh}\n${article.summary_zh}\n来源: ${article.source_name}\n原文: ${article.original_url}`;
                copyTextToClipboard(shareText, "新闻摘要已复制");
            });

            newsGrid.appendChild(card);
        });
    }

    // Open Article Detail Modal
    async function openArticleModal(id) {
        currentArticleId = id;
        try {
            const res = await fetch(`/api/article/${id}`);
            const data = await res.json();
            if (!data.article) return;
            const a = data.article;

            document.getElementById("modal-category").textContent = a.category || "宏观政策";
            const sentPill = document.getElementById("modal-sentiment");
            sentPill.className = `sentiment-pill ${a.sentiment === '利多' ? 'bullish' : (a.sentiment === '利空' ? 'bearish' : 'neutral')}`;
            sentPill.textContent = a.sentiment === '利多' ? '🟢 利多' : (a.sentiment === '利空' ? '🔴 利空' : '⚪ 中性');
            document.getElementById("modal-source").textContent = a.source_name || "Bloomberg";
            
            document.getElementById("modal-title-zh").textContent = a.title_zh || a.title_en;
            document.getElementById("modal-title-en").textContent = a.title_en;
            document.getElementById("modal-date").textContent = formatDate(a.published_at);
            
            const extLink = document.getElementById("modal-external-link");
            extLink.href = a.original_url;

            // Key Points
            const kpList = document.getElementById("modal-key-points-list");
            kpList.innerHTML = "";
            if (a.key_points && a.key_points.length > 0) {
                a.key_points.forEach(pt => {
                    const li = document.createElement("li");
                    li.textContent = pt;
                    kpList.appendChild(li);
                });
                document.getElementById("modal-key-points-box").style.display = "block";
            } else {
                document.getElementById("modal-key-points-box").style.display = "none";
            }

            // Summary / Content
            document.getElementById("modal-content-zh").textContent = a.content_zh || a.summary_zh || a.title_zh;
            
            if (a.content_en) {
                document.getElementById("modal-content-en").textContent = a.content_en;
                document.getElementById("modal-content-en-section").style.display = "block";
            } else {
                document.getElementById("modal-content-en-section").style.display = "none";
            }

            btnCopyModal.onclick = () => {
                const kpText = (a.key_points || []).map(p => `• ${p}`).join("\n");
                const shareText = `【彭博中国财经】${a.title_zh}\n${kpText ? kpText + '\n' : ''}${a.content_zh || a.summary_zh}\n来源: ${a.source_name}\n原文: ${a.original_url}`;
                copyTextToClipboard(shareText, "已复制报道详情");
            };

            articleModal.style.display = "flex";
        } catch (e) {
            showToast("打开新闻详情失败");
        }
    }

    // Fetch Full Text on Demand
    btnFetchFullText.addEventListener("click", async () => {
        if (!currentArticleId) return;
        btnFetchFullText.disabled = true;
        btnFetchFullText.innerHTML = `<div class="spinner"></div> <span>抓取翻译中...</span>`;
        try {
            const res = await fetch(`/api/article/${currentArticleId}/fetch_full`, { method: "POST" });
            const data = await res.json();
            if (data.content_zh) {
                document.getElementById("modal-content-zh").textContent = data.content_zh;
            }
            if (data.content_en) {
                document.getElementById("modal-content-en").textContent = data.content_en;
                document.getElementById("modal-content-en-section").style.display = "block";
            }
            showToast("正文段落已抓取并完成中文翻译");
        } catch (e) {
            showToast("抓取正文失败，请直接访问原报道链接");
        } finally {
            btnFetchFullText.disabled = false;
            btnFetchFullText.innerHTML = `<i class="fa-solid fa-cloud-arrow-down"></i> <span>抓取全文段落</span>`;
        }
    });

    // Mobile Reading Modal
    btnMobile.addEventListener("click", async () => {
        try {
            const res = await fetch("/api/mobile_info");
            const data = await res.json();
            mobileUrlLink.textContent = data.url;
            mobileUrlLink.href = data.url;
            mobileRssLink.textContent = `${data.url}/feed.xml`;
            qrImg.src = `/api/qrcode?t=${Date.now()}`;
            mobileModal.style.display = "flex";
        } catch (e) {
            showToast("获取手机访问信息失败");
        }
    });

    mobileClose.addEventListener("click", () => mobileModal.style.display = "none");
    mobileModal.addEventListener("click", (e) => {
        if (e.target === mobileModal) mobileModal.style.display = "none";
    });

    // Modal Close Events
    modalClose.addEventListener("click", () => articleModal.style.display = "none");
    articleModal.addEventListener("click", (e) => {
        if (e.target === articleModal) articleModal.style.display = "none";
    });

    // Pagination
    function updatePagination() {
        if (totalPages <= 1) {
            paginationBar.style.display = "none";
            return;
        }
        paginationBar.style.display = "flex";
        pageIndicator.textContent = `第 ${currentPage} 页 / 共 ${totalPages} 页`;
        btnPrevPage.disabled = (currentPage <= 1);
        btnNextPage.disabled = (currentPage >= totalPages);
    }

    btnPrevPage.addEventListener("click", () => {
        if (currentPage > 1) {
            currentPage--;
            loadNews();
            window.scrollTo({ top: 0, behavior: 'smooth' });
        }
    });

    btnNextPage.addEventListener("click", () => {
        if (currentPage < totalPages) {
            currentPage++;
            loadNews();
            window.scrollTo({ top: 0, behavior: 'smooth' });
        }
    });

    // Category Switching
    categoryTabs.addEventListener("click", (e) => {
        const tab = e.target.closest(".tab-item");
        if (!tab) return;
        
        categoryTabs.querySelectorAll(".tab-item").forEach(t => t.classList.remove("active"));
        tab.classList.add("active");
        currentCategory = tab.dataset.cat;
        currentPage = 1;
        loadNews();
    });

    // Search Input with Debounce
    let searchTimeout = null;
    searchInput.addEventListener("input", () => {
        const val = searchInput.value.trim();
        clearSearchBtn.style.display = val ? "block" : "none";
        clearTimeout(searchTimeout);
        searchTimeout = setTimeout(() => {
            currentSearch = val;
            currentPage = 1;
            loadNews();
        }, 300);
    });

    clearSearchBtn.addEventListener("click", () => {
        searchInput.value = "";
        clearSearchBtn.style.display = "none";
        currentSearch = "";
        currentPage = 1;
        loadNews();
    });

    // Filters
    filterSentiment.addEventListener("change", () => {
        currentSentiment = filterSentiment.value;
        currentPage = 1;
        loadNews();
    });

    toggleEnglish.addEventListener("change", () => {
        showEnglish = toggleEnglish.checked;
        loadNews();
    });

    toggleChinaOnly.addEventListener("change", () => {
        chinaOnly = toggleChinaOnly.checked;
        currentPage = 1;
        loadNews();
    });

    // Auto Refresh Toggle
    btnAutoRefresh.addEventListener("click", () => {
        autoRefreshEnabled = !autoRefreshEnabled;
        if (autoRefreshEnabled) {
            btnAutoRefresh.classList.add("active");
            autoRefreshCountdown = 60;
            autoRefreshLabel.textContent = `轮询: 60s`;
            autoRefreshTimer = setInterval(() => {
                autoRefreshCountdown--;
                if (autoRefreshCountdown <= 0) {
                    autoRefreshCountdown = 60;
                    loadStats();
                    loadNews();
                }
                autoRefreshLabel.textContent = `轮询: ${autoRefreshCountdown}s`;
            }, 1000);
            showToast("已开启每 60 秒自动刷新");
        } else {
            btnAutoRefresh.classList.remove("active");
            clearInterval(autoRefreshTimer);
            autoRefreshLabel.textContent = "轮询: 关";
            showToast("已关闭自动刷新");
        }
    });

    // Trigger Scrape Button
    btnTriggerScrape.addEventListener("click", async () => {
        btnTriggerScrape.disabled = true;
        scrapeBanner.style.display = "flex";
        showToast("已启动多源抓取，正在检索彭博社与授权辛迪加资讯...");

        try {
            const res = await fetch("/api/scrape", { method: "POST" });
            const data = await res.json();
            
            if (pollInterval) clearInterval(pollInterval);
            pollInterval = setInterval(async () => {
                const statRes = await fetch("/api/scrape_status");
                const statData = await statRes.json();
                if (!statData.is_scraping) {
                    clearInterval(pollInterval);
                    pollInterval = null;
                    scrapeBanner.style.display = "none";
                    btnTriggerScrape.disabled = false;

                    const added = statData.last_result ? statData.last_result.new_added : 0;
                    showToast(`抓取完成！成功入库 ${added} 条最新资讯`);
                    loadStats();
                    loadNews();
                }
            }, 1500);
        } catch (e) {
            btnTriggerScrape.disabled = false;
            scrapeBanner.style.display = "none";
            showToast("抓取请求异常");
        }
    });

    // Settings Modal
    btnSettings.addEventListener("click", async () => {
        try {
            const res = await fetch("/api/settings");
            const data = await res.json();
            document.getElementById("setting-proxy").value = data.proxy_url || "";
            document.getElementById("setting-interval").value = data.scrape_interval || "30";
            document.getElementById("setting-ai-key").value = data.ai_api_key || "";
            document.getElementById("setting-ai-url").value = data.ai_base_url || "";
            document.getElementById("setting-ai-model").value = data.ai_model || "";
            
            const proxyStatusEl = document.getElementById("proxy-status-text");
            if (data.proxy_active) {
                proxyStatusEl.textContent = `本地代理已连接 (${data.proxy_url})`;
            } else {
                proxyStatusEl.textContent = "直连网络 (Bing/辛迪加授权源)";
            }

            settingsModal.style.display = "flex";
        } catch (e) {
            showToast("获取设置失败");
        }
    });

    settingsClose.addEventListener("click", () => settingsModal.style.display = "none");
    settingsModal.addEventListener("click", (e) => {
        if (e.target === settingsModal) settingsModal.style.display = "none";
    });

    btnSaveSettings.addEventListener("click", async () => {
        const payload = {
            proxy_url: document.getElementById("setting-proxy").value.trim(),
            scrape_interval: document.getElementById("setting-interval").value.trim(),
            ai_api_key: document.getElementById("setting-ai-key").value.trim(),
            ai_base_url: document.getElementById("setting-ai-url").value.trim(),
            ai_model: document.getElementById("setting-ai-model").value.trim()
        };

        try {
            const res = await fetch("/api/settings", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });
            const data = await res.json();
            showToast(data.message || "配置已保存");
            settingsModal.style.display = "none";
            loadStats();
        } catch (e) {
            showToast("保存配置失败");
        }
    });

    // Helper functions
    function escapeHtml(str) {
        if (!str) return "";
        return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
    }

    function formatDate(dateStr) {
        if (!dateStr) return "";
        try {
            const d = new Date(dateStr);
            if (isNaN(d.getTime())) return dateStr;
            const now = new Date();
            const diffHours = Math.floor((now - d) / (1000 * 60 * 60));
            if (diffHours < 1) return "刚刚";
            if (diffHours < 24) return `${diffHours}小时前`;
            return `${d.getMonth() + 1}月${d.getDate()}日`;
        } catch {
            return dateStr;
        }
    }

    // Init
    loadStats();
    loadNews();
});
