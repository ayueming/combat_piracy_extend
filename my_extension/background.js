// background.js
import { resolveUrls } from './resolver.js';

const activeTasks = {};
const previewTabs = {}; // ★ 记录预览 Tab 的上下文
let ws = null;
let messageQueue = [];

function connectToPython() {
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return;

    ws = new WebSocket("ws://127.0.0.1:8080");
    ws.onopen = () => {
        console.log("✅ [后台] 成功连接本地 Python WS 服务");
        while (messageQueue.length > 0) ws.send(messageQueue.shift());
    };
    ws.onmessage = (event) => {
        try {
            const msg = JSON.parse(event.data);
            if (msg.action === "do_search") handleDoSearch(msg);

            // ★ 核心：处理打开预览
            if (msg.action === "open_preview") {
                console.log(`[后台] 收到预览请求，正在打开: ${msg.url}`);

                // 查找当前活动的标签页，如果它是唤醒页或者已经打开的预览页，就直接复用
                chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
                    let targetTabId = null;
                    if (tabs.length > 0) {
                        const url = tabs[0].url || "";
                        // 如果是唤醒页，或者已经被我们记录过的预览页，就直接更新 URL
                        if (url.includes("wakeup.html") || previewTabs[tabs[0].id]) {
                            targetTabId = tabs[0].id;
                        }
                    }

                    if (targetTabId) {
                        chrome.tabs.update(targetTabId, { url: msg.url, active: true });
                        previewTabs[targetTabId] = msg;
                        sendPickingContext(targetTabId, msg);
                    } else {
                        chrome.tabs.create({ url: msg.url, active: true }, (newTab) => {
                            previewTabs[newTab.id] = msg;
                            chrome.tabs.onUpdated.addListener(function listener(tabId, info) {
                                if (tabId === newTab.id && info.status === "complete") {
                                    chrome.tabs.onUpdated.removeListener(listener);
                                    sendPickingContext(tabId, msg);
                                }
                            });
                        });
                    }
                });
            }

            if (msg.action === "close_preview") {
                chrome.windows.getCurrent((win) => {
                    chrome.windows.update(win.id, { state: "normal" });
                });
            }
            if (msg.action === "resolve_stale_urls") {
                resolveUrls(msg.links).then(() => {
                    sendToPython({
                        action: "stale_urls_resolved",
                        task_id: msg.task_id,
                        links: msg.links
                    });
                });
            }
        } catch (e) { console.error(e); }
    };
    ws.onclose = () => setTimeout(connectToPython, 3000);
    ws.onerror = (err) => console.error("WS 发生错误:", err);
}
connectToPython();

// 辅助函数：发送上下文给 content.js
function sendPickingContext(tabId, msg) {
    setTimeout(() => {
        chrome.tabs.sendMessage(tabId, {
            action: "start_picking_mode",
            context: {
                book_name: msg.book_name || "",
                keyword: msg.keyword || "",
                batch_id: msg.batch_id || "",
                category: msg.category || "",
                available_books: msg.available_books || [],
                available_categories: msg.available_categories || []
            }
        }).catch(() => {});
    }, 800);
}

// ... 保留原有的 chrome.tabs.onUpdated 里的翻页监听和 handleDoSearch ...

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
    if (changeInfo.status === "complete") {
        for (const [taskId, taskInfo] of Object.entries(activeTasks)) {
            if (taskInfo.tabId === tabId && taskInfo.waiting_for_next_page) {
                taskInfo.waiting_for_next_page = false;
                console.log(`[后台] 翻页完成，唤醒第 ${taskInfo.current_page} 页抓取`);
                setTimeout(() => {
                    chrome.tabs.sendMessage(tabId, {
                        action: "start_scan",
                        task: taskInfo.originalTask,
                        page: taskInfo.current_page
                    }).catch(() => {});
                }, 1000);
            }
        }
    }
});

function handleDoSearch(task) {
    if (activeTasks[task.task_id]) return;
    chrome.windows.getAll({ populate: true }, (windows) => {
        let targetWindow = null;
        let wakeupTab = null;
        for (let win of windows) {
            for (let tab of win.tabs) {
                if (tab.url && tab.url.includes("wakeup.html")) {
                    targetWindow = win;
                    wakeupTab = tab;
                    break;
                }
            }
            if (wakeupTab) break;
        }
        if (wakeupTab) {
            chrome.tabs.create({ windowId: targetWindow.id, url: task.url, active: true }, (newTab) => {
                if (!chrome.runtime.lastError) initTaskAndScan(newTab.id, targetWindow.id, task);
            });
        } else {
            chrome.windows.create({ url: task.url, focused: true, width: 1200, height: 800 }, (win) => {
                if (!chrome.runtime.lastError) initTaskAndScan(win.tabs[0].id, win.id, task);
            });
        }
    });
}

function initTaskAndScan(tabId, windowId, task) {
    activeTasks[task.task_id] = { tabId, windowId, originalTask: task, current_page: 1, waiting_for_next_page: false };
    let listener = (updatedTabId, info) => {
        if (updatedTabId !== tabId || info.status !== "complete") return;
        chrome.tabs.onUpdated.removeListener(listener);
        setTimeout(() => {
            chrome.tabs.sendMessage(tabId, { action: "start_scan", task: task, page: 1 }).catch(() => {});
        }, 1000);
    };
    chrome.tabs.onUpdated.addListener(listener);
}

function sendToPython(data) {
    let msgStr = JSON.stringify(data);
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(msgStr);
    } else {
        messageQueue.push(msgStr);
        connectToPython();
    }
}

async function processAndSendScanResult(data) {
    const links = data.links;

    // ★ 15秒超时保护：如果隐藏页迟迟不跳转，强制停止等待
    const timeoutPromise = new Promise((resolve) => {
        setTimeout(() => {
            console.warn("⚠️ [后台] 解析超时(15秒)，强制携带原链接发送");
            resolve();
        }, 15000);
    });

    // 竞速：要么解析完，要么超时
    await Promise.race([resolveUrls(links), timeoutPromise]);

    sendToPython(data);
}

// 统一消息路由
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === "send_to_python") {
        let d = request.data || {};

        // 手动拾取拦截
        if (d.action === "manual_pick" && sender.tab) {
            const tabInfo = previewTabs[sender.tab.id];
            if (!d.parent_url && tabInfo) {
                d.parent_url = tabInfo.url;
                d.parent_title = tabInfo.book_name ? `${tabInfo.book_name}的相关页面` : "";
            }
            if (!d.batch_id && tabInfo) {
                d.batch_id = tabInfo.batch_id;
            }
            console.log(`[后台] 收到手动拾取: ${d.url}`);
            sendToPython(d);
            return true;
        }

        // 保存本批
        if (d.action === "save_manual_batch" && sender.tab) {
            const tabInfo = previewTabs[sender.tab.id];
            if (!d.batch_id && tabInfo) {
                d.batch_id = tabInfo.batch_id;
            }
            console.log(`[后台] 用户点击保存本批: ${d.batch_id}`);
            sendToPython(d);
            return true;
        }

        if (d.action === "request_next_page" && d.task_id) {
            if (activeTasks[d.task_id]) {
                activeTasks[d.task_id].current_page += 1;
                activeTasks[d.task_id].waiting_for_next_page = true;
            }
            return true;
        }

        if (d.action === "scan_finished" && d.task_id) {
            if (activeTasks[d.task_id]) {
                const taskInfo = activeTasks[d.task_id];
                if (taskInfo.tabId) chrome.tabs.remove(taskInfo.tabId).catch(() => {});
                delete activeTasks[d.task_id];
            }
            sendToPython(d);
            return true;
        }

        if (d.action === "scan_result" && d.links && d.links.length > 0) {
            processAndSendScanResult(d).then(() => {
                // ★ 解析完成或超时，给 content.js 回执
                sendResponse({ ok: true });
            }).catch(() => {
                sendResponse({ ok: false });
            });
            return true; // 保持消息通道打开，等待异步完成
        }

        sendToPython(d);
    }
    return true;
});

// ==================== 新增：保活机制 ====================
chrome.alarms.create("keepAlive", { periodInMinutes: 1 });

chrome.alarms.onAlarm.addListener((alarm) => {
    if (alarm.name === "keepAlive") {
        if (!ws || ws.readyState !== WebSocket.OPEN) {
            console.log("⏰ [保活] 发现连接断开，尝试重连...");
            connectToPython();
        }
    }
});