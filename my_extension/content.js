// content.js
console.log("🚀 插件执行端已注入（搜索抓取 + 手动拾取）");
let _isScanning = false;
let _expecting_reload = false;

// ==========================================
// 0. 全局暂存区（用于瀑布流边滚边抓去重）
// ==========================================
let globalScannedLinks = new Map();

// ==========================================
// 1. 自动搜索抓取逻辑
// ==========================================
async function humanScroll(maxPages, doScan) {
    return new Promise(async (resolve) => {
        // 按数量折算：1页 = 10条
        const targetCount = maxPages * 10;
        console.log(`📜 开始模拟人类阅读，目标折算数量: ${targetCount} 条`);

        let scrollSteps = 0;
        const maxTotalSteps = maxPages * 5 + 5; // 兜底最大滚动次数，防止死循环
        let emptyScrollCount = 0; // 连续空滚次数
        let lastItemCount = 0;

        // 辅助函数：寻找真正的滚动容器（自动适配 Edge/Chrome/夸克）
        const findScrollableContainer = () => {
            // 适配新版贴吧的内部滚动盒
            let target = document.querySelector('.thread-list-container, .pb-content, .forum-list, #thread_list');
            if (target && target.scrollHeight > target.clientHeight) return target;

            // 兜底：遍历找最大的可滚动 div
            let maxScroll = 0;
            let scrollEl = window;
            document.querySelectorAll('div').forEach(el => {
                if (el.scrollHeight > el.clientHeight && el.clientHeight > 300 && getComputedStyle(el).overflowY !== 'hidden') {
                    if (el.scrollHeight > maxScroll) {
                        maxScroll = el.scrollHeight;
                        scrollEl = el;
                    }
                }
            });
            return scrollEl;
        };

        // 辅助函数：收集数据并去重
        const collectData = () => {
            let currentLinks = doScan();
            if (!currentLinks || currentLinks.length === 0) return 0;

            let newCount = 0;
            currentLinks.forEach(link => {
                if (!globalScannedLinks.has(link.url)) {
                    globalScannedLinks.set(link.url, link);
                    newCount++;
                }
            });
            if (newCount > 0) {
                console.log(`[抓取] 新增 ${newCount} 条，当前总提取: ${globalScannedLinks.size} 条`);
            }
            return newCount;
        };

        // 初始化先抓一次当前屏幕上的数据
        collectData();
        lastItemCount = globalScannedLinks.size;

        while (scrollSteps < maxTotalSteps) {
            let currentCount = globalScannedLinks.size;
            if (currentCount >= targetCount) {
                console.log(`🎯 已达到目标数量 (${targetCount} 条)，结束滚动`);
                break;
            }

            let scrollEl = findScrollableContainer();

            // 拟人化滚动：随机距离 (0.6屏 ~ 1.2屏)
            let downDist = window.innerHeight * (0.6 + Math.random() * 0.6);

            // ★ 动作A：原生滚动
            if (scrollEl === window || scrollEl === document.documentElement) {
                window.scrollBy({ top: downDist, behavior: 'smooth' });
            } else {
                scrollEl.scrollBy({ top: downDist, behavior: 'smooth' });
            }

            // ★ 动作B：终极防封兼触发加载：发射鼠标滚轮事件（针对夸克这种顽固派）
            const wheelEvent = new WheelEvent('wheel', {
                deltaY: downDist,
                deltaMode: 0,
                bubbles: true,
                cancelable: true
            });
            document.dispatchEvent(wheelEvent);
            document.body.dispatchEvent(wheelEvent);

            // ★ 动作C：如果是夸克，再补一个 PageDown 键（向下翻页）
            document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'PageDown', keyCode: 34, which: 34, bubbles: true }));

            // 随机阅读停顿时间 (1.5秒 ~ 2.5秒)
            await new Promise(r => setTimeout(r, 1500 + Math.random() * 1000));
            scrollSteps++;

            // ★ 核心：滚完立刻抓一把当前页面的数据
            collectData();
            let currentTotal = globalScannedLinks.size;

            // 判断是否彻底到底（数量不再增加）
            if (currentTotal === lastItemCount) {
                emptyScrollCount++;
            } else {
                emptyScrollCount = 0;
                lastItemCount = currentTotal;
            }

            if (emptyScrollCount >= 3) {
                console.log("🛑 连续多次未抓到新数据，等待 3 秒做最终确认...");
                await new Promise(r => setTimeout(r, 3000));
                collectData(); // 最后再捞一次
                if (globalScannedLinks.size === lastItemCount) {
                    console.log("🛑 确认见底，结束滚动");
                    break;
                }
            }
        }

        console.log(`📜 滚动结束（共执行 ${scrollSteps} 步），最终收集到 ${globalScannedLinks.size} 条数据`);
        resolve();
    });
}

// ★ 新增：通用智能来源提取器
function extractSourceSite(container, strategy, href, title) {
    // 1. 首先尝试使用配置的选择器（保持各个平台基础准确性）
    if (strategy.sourceSelector) {
        let sourceEl = container.querySelector(strategy.sourceSelector);
        if (sourceEl) {
            let txt = sourceEl.innerText.replace(/\s+/g, '').trim();
            if (txt && !txt.includes("http")) return txt;
        }
    }

    // 2. 通用智能兜底：抓取所有 class 或 id 里带有 source、site、from 字眼的标签
    let genericSelectors = [
        '[class*="source-item"]', '[class*="source"]',
        '[class*="site"]', '[class*="from"]'
    ];
    for (let sel of genericSelectors) {
        let els = container.querySelectorAll(sel);
        for (let el of els) {
            let txt = el.innerText.replace(/\s+/g, '').trim();
            // 过滤：有字、不太长、不是链接、不是标题本身
            if (txt && txt.length > 0 && txt.length < 20 && !txt.includes("http") && !txt.includes("www.") && !title.includes(txt)) {
                return txt;
            }
        }
    }

    // 3. 终极暴力兜底：找当前卡片里所有短文本（2-10个字），排除掉噪音词
    let candidates = [];
    let allNodes = container.querySelectorAll('*');
    for (let node of allNodes) {
        if (node.children.length > 0) continue;
        let text = node.innerText.replace(/\s+/g, '').trim();
        if (text && text.length >= 2 && text.length <= 10 &&
            !text.includes('http') && !text.includes('www') && !text.includes('.com') &&
            !title.includes(text) && !text.includes('作者') && !text.includes('类型')) {
            candidates.push(text);
        }
    }
    if (candidates.length > 0) {
        return candidates[candidates.length - 1]; // 通常来源在偏下方
    }

    // 4. 彻底找不到，提取域名
    try {
        let host = new URL(href).hostname;
        return host.replace('www.', '');
    } catch(e){ return ""; }
}

function scanGeneric(strategy) {
    let linksData = [];
    if (!strategy || !strategy.resultSelector) return linksData;

    document.querySelectorAll(strategy.resultSelector).forEach(container => {
        let titleLink = container.querySelector(strategy.titleSelector);
        if (!titleLink) return;
        let href = titleLink.getAttribute('data-landurl') || titleLink.getAttribute('mu') || titleLink.href;
        if (!href || !href.startsWith("http")) return;
        let title = (titleLink.innerText || "").replace(/\s+/g, ' ').trim();
        if (!title) return;

        let bodyText = "";
        if (strategy.bodySelector) {
            let bodyEl = container.querySelector(strategy.bodySelector);
            if (bodyEl) {
                bodyText = bodyEl.innerText.trim();
                bodyText = bodyText.replace(/^(合|答|回答|最佳回答)[:：]\s*/, '');
            }
        }

        // ★ 调用通用提取器
        let sourceSite = extractSourceSite(container, strategy, href, title);

        linksData.push({ url: href, title: title, body: bodyText, source_site: sourceSite });
    });
    return linksData;
}

function scanTieba() {
    let rawLinks = [];
    // ★ 双选择器兼容老版(Chrome)与新版(Edge)结构
    const cardRoots = document.querySelectorAll('.threadcardclass.index-feed-cards, .thread-content-box');
    const seenUrls = new Set();

    cardRoots.forEach(threadCard => {
        // 优先从外层属性取标题，如果取不到再从内部 span 找
        let title = threadCard.getAttribute('title') || '';
        if (!title) {
            const titleEl = threadCard.querySelector('.title-wrap span');
            if (titleEl) title = (titleEl.innerText || '').trim();
        }
        if (!title) return;

        const linkEl = threadCard.querySelector('a[href*="/p/"]');
        if (!linkEl) return;
        let postUrl = linkEl.href;

        const match = postUrl.match(/(https?:\/\/tieba\.baidu\.com\/p\/\d+)/);
        if (match) {
            postUrl = match[1];
        } else {
            return;
        }

        if (seenUrls.has(postUrl)) return;
        seenUrls.add(postUrl);

        const bodyEl = threadCard.querySelector('.abstract-wrap span');
        let bodyText = bodyEl ? (bodyEl.innerText || "").trim() : "";

        const forumEl = threadCard.querySelector('.forum-name-text');
        let sourceSite = forumEl ? (forumEl.innerText || "").trim() : "百度贴吧";

        rawLinks.push({ url: postUrl, title: title, body: bodyText, source_site: sourceSite });
    });
    return rawLinks;
}

function sendScanResult(task, links) {
    return new Promise((resolve) => {
        if (!links || links.length === 0) return resolve();
        console.log(`📤 抓取到 ${links.length} 条，等待后台解析回执...`);
        chrome.runtime.sendMessage({
            action: "send_to_python",
            data: { action: "scan_result", task_id: task.task_id, batch_id: task.batch_id, is_manual: false, links: links }
        }, (response) => {
            // 无论后台解析成功还是失败，都等它处理完了再 resolve
            console.log("✅ 后台解析已处理完毕，继续后续流程");
            resolve();
        });
    });
}

function sendHeartbeat(task) {
    chrome.runtime.sendMessage({
        action: "send_to_python",
        data: { action: "scan_heartbeat", task_id: task.task_id, batch_id: task.batch_id }
    });
}

async function startAutoScan(task, current_page) {
    if (_isScanning) return;
    _isScanning = true;
    _expecting_reload = false;

    try {
        const strategy = task.strategy || {};
        const maxPages = task.max_pages || 3;
        const scanner = strategy.scanner || "generic";
        const doScan = () => scanner === "tieba" ? scanTieba() : scanGeneric(strategy);

        let initialWait = current_page === 1 ? Math.random() * 2000 : 500;
        await new Promise(r => setTimeout(r, initialWait));

        if (strategy.mode === "click") {
            console.log(`📄 处理第 ${current_page} 页...`);

            // ★ 改造 1：非匀速分段滑到底部（模拟滚轮阻尼感）
            let totalHeight = document.body.scrollHeight;
            let currentY = window.scrollY;

            while (currentY < totalHeight - window.innerHeight) {
                // 每次滑动距离不一样 (300px ~ 800px)
                let scrollStep = 300 + Math.random() * 500;
                currentY += scrollStep;
                window.scrollTo({ top: currentY, behavior: 'instant' }); // instant 配合微小的 sleep，看起来像人滚轮滑动的卡顿感

                // 每滑一段，随机停顿 50-150 毫秒
                await new Promise(r => setTimeout(r, 50 + Math.random() * 100));

                // 重新获取高度，防止有懒加载导致页面被拉长
                totalHeight = document.body.scrollHeight;
            }
            // 最后补一个平滑动效，确保稳稳停在最底部
            window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });

            // ★ 改造 2：随机停 0 - 2 秒就抓取
            const waitBeforeScan = Math.random() * 2000;
            console.log(`⏱️ 滑到底部，随机停留 ${(waitBeforeScan/1000).toFixed(1)} 秒后开始抓取...`);
            await new Promise(r => setTimeout(r, waitBeforeScan));

            // 开始提取本页数据
            await sendScanResult(task, doScan());

            // 翻页逻辑
            if (current_page < maxPages) {
                let nextBtn = null;
                for (let i = 0; i < 10; i++) {
                    const candidates = Array.from(document.querySelectorAll(strategy.nextBtnSelector));
                    nextBtn = candidates.find(el => {
                        const text = (el.innerText || "").trim();
                        const className = el.className || "";
                        const isDisabled = el.classList.contains("disabled") || el.disabled;
                        const isNext = className.includes("next") || text.includes("下一页") || text === ">";
                        const isPrev = className.includes("prev") || text.includes("上一页") || text === "<";
                        return !isDisabled && isNext && !isPrev;
                    });
                    if (nextBtn) break;
                    await new Promise(r => setTimeout(r, 500));
                }

                if (nextBtn) {
                    chrome.runtime.sendMessage({
                        action: "send_to_python",
                        data: { action: "request_next_page", task_id: task.task_id }
                    });

                    // ★ 改造 3：取消之前漫长的 2-4 秒犹豫，改为随机 0.3 - 1 秒，直接点！
                    const hesitateMs = 300 + Math.random() * 700;
                    console.log(`🖱️ 准备翻页，停顿 ${(hesitateMs/1000).toFixed(1)} 秒...`);
                    await new Promise(r => setTimeout(r, hesitateMs));

                    _expecting_reload = true;
                    nextBtn.click();
                    return;
                } else {
                    console.log("⚠️ 未找到下一页按钮，提前结束");
                }
            }
        } else if (strategy.mode === "scroll") {
            console.log(`📜 开始瀑布流滚动抓取 (参数限制 ${maxPages} 页)...`);

            // ★ 每次开始新任务前，清空上一轮的全局缓存
            globalScannedLinks.clear();

            // ★ 把 doScan 传进去，实现边滚边抓
            await humanScroll(maxPages, doScan);

            // ★ 滚动结束后，直接从全局缓存打包发送，不再依赖最后一次的 DOM
            let finalLinks = Array.from(globalScannedLinks.values());
            console.log(`📤 滚动结束，最终提取到 ${finalLinks.length} 条，发送给 Python...`);

            await sendScanResult(task, finalLinks);

            // 给 Python 留 2 秒接收时间
            await new Promise(r => setTimeout(r, 2000));
        }
    } catch (e) {
        console.error("扫描异常", e);
    } finally {
        _isScanning = false;
        if (!_expecting_reload) {
            chrome.runtime.sendMessage({
                action: "send_to_python",
                data: { action: "scan_finished", task_id: task.task_id, batch_id: task.batch_id }
            });
            console.log("✅ scan_finished 已发送");
        } else {
            console.log("⏭️ 翻页中，跳过 scan_finished");
        }
    }
}


// ==========================================
// 2. 浮窗拾取器 UI（带拖拽 + 下拉框）
// ==========================================
let pickerState = {
    injected: false,
    picking: false,
    hoverEl: null,
    savedCount: 0,
    ctx: null,
    host: null,
    shadow: null
};

function initPicker(ctx) {
    if (pickerState.injected) {
        applyPickerContext(ctx);
        return;
    }
    pickerState.injected = true;
    pickerState.ctx = ctx;

    // 记录历史栈用于溯源
    let navHistory = [];
    try {
        const saved = sessionStorage.getItem("__aptNavHistory");
        if (saved) navHistory = JSON.parse(saved);
    } catch(e) {}
    const curPage = { url: location.href, title: document.title || "" };
    if (navHistory.length === 0 || navHistory[navHistory.length - 1].url !== curPage.url) {
        navHistory.push(curPage);
        if (navHistory.length > 10) navHistory.shift();
        try { sessionStorage.setItem("__aptNavHistory", JSON.stringify(navHistory)); } catch(e) {}
    }

    const host = document.createElement("div");
    host.id = "__apt_picker_host__";
    // 初始定位在右下角
    host.style.cssText = "all: initial; position:fixed; right:20px; bottom:20px; z-index:2147483647; font-family:Microsoft YaHei,Arial,sans-serif;";

    const parent = document.body || document.documentElement;
    if (!parent) { setTimeout(() => initPicker(ctx), 50); return; }
    parent.appendChild(host);

    const shadow = host.attachShadow({ mode: "closed" });
    pickerState.host = host;
    pickerState.shadow = shadow;

    // 注入 CSS
    const style = document.createElement("style");
    style.textContent = `
        :host, * { box-sizing: border-box; }
        .panel { width: 240px; background: #ffffff; border: 1px solid #d0d7de; border-radius: 8px; box-shadow: 0 4px 16px rgba(0,0,0,.12); font-size: 12px; color: #24292f; overflow: hidden; pointer-events: auto !important; }
        .head { background: #f6f8fa; padding: 8px 10px; font-weight: 600; border-bottom: 1px solid #eaeef2; display: flex; justify-content: space-between; align-items: center; cursor: move; user-select: none; }
        .head span { cursor: move; }
        .ctx-area { padding: 8px 10px; border-bottom: 1px solid #eaeef2; display: flex; flex-direction: column; gap: 6px; }
        .ctx-row { display: flex; align-items: center; justify-content: space-between; }
        .ctx-row label { color: #57606a; font-weight: 600; }
        .ctx-row select { flex: 1; margin-left: 8px; padding: 2px 4px; border: 1px solid #d0d7de; border-radius: 4px; font-size: 12px; background: white; }
        .ctx-kw { color: #57606a; word-break: break-all; }
        .ctx-kw b { color: #24292f; }
        .actions { display: flex; flex-direction: column; gap: 6px; padding: 8px 10px; }
        button { padding: 6px 0; border-radius: 5px; cursor: pointer !important; font-size: 12px; font-weight: 600; border: 1px solid transparent; font-family: inherit; pointer-events: auto !important; }
        .btn-save-page { background: #f6f8fa; color: #24292f; border-color: #d0d7de; }
        .btn-save-page:hover { background: #eaeef2; }
        .btn-pick { background: #f6f8fa; color: #24292f; border-color: #d0d7de; }
        .btn-pick:hover { background: #eaeef2; }
        .btn-pick.active { background: #fff8c5; border-color: #d4a72c; color: #7d4e00; }
        .btn-save-batch { background: #10B981; color: #fff; margin-top: 4px; }
        .btn-save-batch:hover { background: #059669; }
        .status { padding: 6px 10px; background: #f6f8fa; color: #57606a; font-size: 11px; }
    `;
    shadow.appendChild(style);

    const panel = document.createElement("div");
    panel.className = "panel";

    // 头部（拖拽把手）
    const head = document.createElement("div");
    head.className = "head";
    head.innerHTML = `<span>反盗版助手 · 拾取</span>`;
    panel.appendChild(head);

    // 上下文区（带下拉框）
    const ctxArea = document.createElement("div");
    ctxArea.className = "ctx-area";
    ctxArea.innerHTML = `
        <div class="ctx-row">
            <label>作品:</label>
            <select id="apt-book"></select>
        </div>
        <!-- ★ 加上隐藏样式，保留 DOM 结构 -->
        <div class="ctx-row" style="display: none;">
            <label>分类:</label>
            <select id="apt-category"></select>
        </div>
        <div class="ctx-kw">关键词: <b id="apt-kw">-</b></div>
    `;
    panel.appendChild(ctxArea);

    // 按钮区
    const actions = document.createElement("div");
    actions.className = "actions";

    const btnSavePage = document.createElement("button");
    btnSavePage.className = "btn-save-page";
    btnSavePage.textContent = "仅保存当前网址";

    const btnPick = document.createElement("button");
    btnPick.className = "btn-pick";
    btnPick.textContent = "手动拾取链接（或按住ALT）";

    const btnSaveBatch = document.createElement("button");
    btnSaveBatch.className = "btn-save-batch";
    btnSaveBatch.textContent = "💾 保存本批";

    actions.appendChild(btnSavePage);
    actions.appendChild(btnPick);
    actions.appendChild(btnSaveBatch);
    panel.appendChild(actions);

    // 状态区
    const status = document.createElement("div");
    status.className = "status";
    status.innerHTML = `待保存 <b id="apt-count">0</b> 条`;
    panel.appendChild(status);

    shadow.appendChild(panel);

    // 遮罩层
    const mask = document.createElement("div");
    mask.style.cssText = "all: initial; position:fixed; top:0; left:0; width:100vw; height:100vh; z-index:2147483645; background:transparent; display:none; cursor:crosshair;";
    document.body.appendChild(mask);

    // 高亮框
    const overlay = document.createElement("div");
    overlay.style.cssText = "all: initial; position:fixed; pointer-events:none; border:2px solid #1f6feb; background:rgba(31,111,235,.12); border-radius:3px; display:none; z-index:2147483646; transition:all .08s ease;";
    document.body.appendChild(overlay);

    // 应用上下文
    applyPickerContext(ctx);

    // ===== 拖拽逻辑 =====
    let isDragging = false;
    let dragStartX, dragStartY, initialLeft, initialTop;

    head.addEventListener("mousedown", (e) => {
        if (e.target.tagName === "BUTTON") return;
        isDragging = true;
        dragStartX = e.clientX;
        dragStartY = e.clientY;
        const rect = host.getBoundingClientRect();
        initialLeft = rect.left;
        initialTop = rect.top;
        // 固定转换为绝对定位
        host.style.left = initialLeft + "px";
        host.style.top = initialTop + "px";
        host.style.right = "auto";
        host.style.bottom = "auto";
        e.preventDefault();
    });

    document.addEventListener("mousemove", (e) => {
        if (!isDragging) return;
        const dx = e.clientX - dragStartX;
        const dy = e.clientY - dragStartY;
        host.style.left = (initialLeft + dx) + "px";
        host.style.top = (initialTop + dy) + "px";
    });

    document.addEventListener("mouseup", () => {
        isDragging = false;
    });

    // ===== 拾取逻辑 =====
    function enterPicking(source) {
        pickerState.picking = true;
        btnPick.classList.add("active");
        btnPick.textContent = "🔴 拾取中（点击退出）";
        mask.style.display = "block";
        host.style.borderLeft = "4px solid #EF4444";
    }

    function exitPicking() {
        pickerState.picking = false;
        btnPick.classList.remove("active");
        btnPick.textContent = "手动拾取链接（或按住ALT）";
        mask.style.display = "none";
        overlay.style.display = "none";
        host.style.borderLeft = "";
        pickerState.hoverEl = null;
    }

    btnPick.addEventListener("click", (e) => {
        e.preventDefault(); e.stopPropagation();
        if (pickerState.picking) exitPicking(); else enterPicking();
    });

    btnSavePage.addEventListener("click", (e) => {
        e.preventDefault(); e.stopPropagation();
        sendManualPick({
            url: finalUrl,
            title: titleText,
            body: bodyText,
            parent_url: p_url,
            parent_title: p_title
        });

        // ★ 新增：获取当前选中的关联作品名
        const selBook = pickerState.shadow?.getElementById("apt-book");
        const currentBookName = selBook ? selBook.value : (pickerState.ctx?.book_name || "未选择作品");

        // ★ 新增：处理 URL 长度，防止 Toast 提示框太长飞出屏幕
        let displayUrl = finalUrl;
        if (displayUrl.length > 30) {
            displayUrl = displayUrl.substring(0, 30) + "...";
        }

        // ★ 修改：物尽其用 Toast，显示作品和截断的 URL
        showToast(`✅ 已拾取《${currentBookName}》 - ${displayUrl}`);

        // 拾取成功后可以选择退出拾取模式，避免连续误触。
        // exitPicking();
    }, true);

    btnSaveBatch.addEventListener("click", (e) => {
        e.preventDefault(); e.stopPropagation();
        chrome.runtime.sendMessage({
            action: "send_to_python",
            data: { action: "save_manual_batch", batch_id: pickerState.ctx?.batch_id || "" }
        });

        pickerState.savedCount = 0;
        const countEl = pickerState.shadow?.getElementById("apt-count");
        if (countEl) countEl.textContent = "0";

        showToast("正在保存本批并解析...");
    });

    function isEditable(el) { const t = el.tagName; return t === "INPUT" || t === "TEXTAREA" || el.isContentEditable; }

    function findLink(el) {
        let cur = el;
        while (cur && cur !== document.documentElement) {
            if (cur.tagName === "A" && cur.href) return cur;
            cur = cur.parentElement;
        }
        let txt = (el.innerText || el.textContent || "").trim();
        if (/https?:\/\//.test(txt)) return el;
        if (location.hostname === "tieba.baidu.com") {
            const card = el.closest(".threadcardclass.index-feed-cards, .thread-content-box");
            if (card) {
                const postLink = card.querySelector("a[href*='/p/']");
                if (postLink) return postLink;
            }
        }
        return null;
    }

    // Alt 瞬态拾取
    let altHoldTimer = null;
    document.addEventListener("keydown", (e) => {
        if (e.key !== "Alt" || e.repeat || isEditable(e.target)) return;
        if (pickerState.picking || altHoldTimer) return;
        altHoldTimer = setTimeout(() => {
            altHoldTimer = null;
            enterPicking();
        }, 120);
    }, true);
    document.addEventListener("keyup", (e) => {
        if (e.key === "Alt") {
            if (altHoldTimer) { clearTimeout(altHoldTimer); altHoldTimer = null; }
            exitPicking();
        }
    }, true);

    mask.addEventListener("mousemove", (e) => {
        if (!pickerState.picking) return;
        mask.style.pointerEvents = "none";
        const realTarget = document.elementFromPoint(e.clientX, e.clientY);
        mask.style.pointerEvents = "auto";
        if (!realTarget) { overlay.style.display = "none"; return; }

        const link = findLink(realTarget);
        if (!link) { overlay.style.display = "none"; pickerState.hoverEl = null; return; }

        if (link !== pickerState.hoverEl) {
            pickerState.hoverEl = link;
            const r = link.getBoundingClientRect();
            overlay.style.left = r.left + "px"; overlay.style.top = r.top + "px";
            overlay.style.width = r.width + "px"; overlay.style.height = r.height + "px";
            overlay.style.display = "block";
        }
    }, true);

    mask.addEventListener("mousedown", (e) => {
        if (!pickerState.picking) return;
        mask.style.pointerEvents = "none";
        const realTarget = document.elementFromPoint(e.clientX, e.clientY);
        mask.style.pointerEvents = "auto";
        if (!realTarget) return;

        e.preventDefault(); e.stopPropagation();

        // 1. 拿链接：优先找最近的 <a> 标签，如果没有，或者 a 标签没 href，就靠后续的正则抠
        let finalUrl = "";
        let curNode = realTarget;
        while (curNode && curNode !== document.documentElement) {
            if (curNode.tagName === "A" && curNode.href) {
                finalUrl = curNode.href;
                break;
            }
            curNode = curNode.parentElement;
        }

        // 2. 拿文本：尝试向上找 3 层，尽量把一整段话都抓下来（避免只抓到一两个字）
        let targetForText = realTarget;
        for (let i = 0; i < 3; i++) {
            if (targetForText.parentElement && targetForText.parentElement.innerText.length < 1000) {
                targetForText = targetForText.parentElement;
            } else {
                break;
            }
        }
        let bodyText = (targetForText.innerText || targetForText.textContent || "").trim();

        // 3. 如果还没链接，尝试从文本里用正则抠出第一个 http 链接
        if (!finalUrl) {
            const match = bodyText.match(/https?:\/\/[a-zA-Z0-9\-\._~:\/?#\[\]@!\$&'\(\)\*\+,;=%]+/);
            if (match) {
                finalUrl = match[0];
            }
        }

        // 4. 校验：必须是个合法的 URL
        if (!finalUrl || !/^https?:\/\//i.test(finalUrl)) {
            showToast("❌ 未识别到有效 URL，请重新拾取");
            return;
        }

        // 5. 标题拿网页标题，或者截取一段文本
        let titleText = document.title || "未命名网页";
        if (bodyText.length > 0 && bodyText.length < 50) {
            titleText = bodyText; // 如果点中的是短文本（比如帖子的标题），直接用作 title
        }

        // 溯源
        let p_url = "";
        let p_title = "";
        if (document.referrer) {
            p_url = document.referrer;
        } else {
            let parentNode = navHistory.length >= 2 ? navHistory[navHistory.length - 2] : null;
            if (parentNode) { p_url = parentNode.url; p_title = parentNode.title; }
            else { p_url = window.location.href; p_title = document.title || ""; }
        }

        // 6. 发送，物尽其用 Toast
        sendManualPick({
            url: finalUrl,
            title: titleText,
            body: bodyText,  // ★ 把抓取到的所有文本作为 body 传给后端
            parent_url: p_url,
            parent_title: p_title
        });

        showToast("✅ 已拾取关联作品 URL");

        // 拾取成功后可以选择退出拾取模式，避免连续误触。如果你希望连续拾取，就注释掉下面这行。
        // exitPicking();
    }, true);
}

// 更新上下文（书籍、分类、关键词）
function applyPickerContext(ctx) {
    pickerState.ctx = ctx || {};
    if (!pickerState.shadow) return;

    const selBook = pickerState.shadow.getElementById("apt-book");
    const selCat = pickerState.shadow.getElementById("apt-category");
    const kwEl = pickerState.shadow.getElementById("apt-kw");

    if (kwEl) kwEl.textContent = ctx.keyword || "-";

    // 填作品
    if (selBook) {
        selBook.innerHTML = "";
        (ctx.available_books || []).forEach(name => {
            const opt = document.createElement("option");
            opt.value = name;
            opt.textContent = name;
            if (name === ctx.book_name) opt.selected = true;
            selBook.appendChild(opt);
        });
        if (!ctx.available_books?.length) {
            const opt = document.createElement("option");
            opt.value = ctx.book_name || "未选择";
            opt.textContent = ctx.book_name || "未选择";
            selBook.appendChild(opt);
        }
    }

    // 填分类
    if (selCat) {
        selCat.innerHTML = "";
        (ctx.available_categories || []).forEach(name => {
            const opt = document.createElement("option");
            opt.value = name;
            opt.textContent = name;
            if (name === ctx.category) opt.selected = true;
            selCat.appendChild(opt);
        });
        if (!ctx.available_categories?.length) {
            const opt = document.createElement("option");
            opt.value = ctx.category || "其他";
            opt.textContent = ctx.category || "其他";
            selCat.appendChild(opt);
        }
    }
}

// 弹出 Toast 提示
function showToast(msg) {
    if (!pickerState.shadow) return;
    let toast = pickerState.shadow.getElementById("__apt_toast__");
    if (!toast) {
        toast = document.createElement("div");
        toast.id = "__apt_toast__";
        toast.style.cssText = "position:fixed; right:20px; bottom:180px; z-index:2147483647; padding:8px 12px; background:rgba(0,0,0,.82); color:#fff; border-radius:6px; font-size:12px; display:none; max-width:260px; font-family:Microsoft YaHei,Arial,sans-serif;";
        pickerState.shadow.appendChild(toast);
    }
    toast.textContent = msg;
    toast.style.display = "block";
    clearTimeout(toast._t);
    toast._t = setTimeout(() => { toast.style.display = "none"; }, 2500);
}

// 发送拾取数据到 Python
function sendManualPick(link) {
    const selBook = pickerState.shadow?.getElementById("apt-book");
    const selCat = pickerState.shadow?.getElementById("apt-category");

    // ★ 核心判断：先看下拉框的值（虽然隐藏了但数据在），如果没有，再用内存里的上下文
    let finalCategory = "";
    if (selCat && selCat.value) {
        finalCategory = selCat.value;
    } else if (pickerState.ctx && pickerState.ctx.category) {
        finalCategory = pickerState.ctx.category;
    }

    chrome.runtime.sendMessage({
        action: "send_to_python",
        data: {
            action: "manual_pick",
            url: link.url,
            title: link.title,
            body: link.body || "",
            source_site: link.source_site || "",
            parent_url: link.parent_url || "",
            parent_title: link.parent_title || "",
            book_name: selBook ? selBook.value : "",
            category: finalCategory // ★ 发送确定好的分类
        }
    });

    // 更新计数
    pickerState.savedCount++;
    const countEl = pickerState.shadow?.getElementById("apt-count");
    if (countEl) countEl.textContent = String(pickerState.savedCount);
}


// ==========================================
// 3. 消息路由
// ==========================================
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    // 自动搜索
    if (request.action === "start_scan") {
        const task = request.task;
        const page = request.page || 1;
        startAutoScan(task, page);
        sendResponse({ ok: true });
    }

    // 拾取模式启动（由 background.js 在预览 Tab 打开时下发）
    if (request.action === "start_picking_mode") {
        const ctx = request.context || {};
        // 保存一份到 sessionStorage，防止页面刷新后丢失
        try {
            sessionStorage.setItem("__aptPreviewCtx", JSON.stringify(ctx));
            sessionStorage.setItem("__aptIsPreview", "1");
        } catch(e) {}

        if (document.readyState === "loading") {
            document.addEventListener("DOMContentLoaded", () => initPicker(ctx));
        } else {
            initPicker(ctx);
        }
        sendResponse({ ok: true });
    }

    // 上下文更新（可选）
    if (request.action === "update_context") {
        applyPickerContext(request.data || {});
        sendResponse({ ok: true });
    }
});

// ==========================================
// 4. 页面加载时：自动检测是否是预览页
// ==========================================
(function autoRecoverPicker() {
    try {
        if (sessionStorage.getItem("__aptIsPreview") === "1") {
            const ctxStr = sessionStorage.getItem("__aptPreviewCtx");
            if (ctxStr) {
                const ctx = JSON.parse(ctxStr);
                if (document.readyState === "loading") {
                    document.addEventListener("DOMContentLoaded", () => initPicker(ctx));
                } else {
                    initPicker(ctx);
                }
            }
        }
    } catch(e) {}
})();