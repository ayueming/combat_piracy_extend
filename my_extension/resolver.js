// my_extension/resolver.js

let resolveQueue = [];
let isProcessingQueue = false;
let lastHiddenTabOpenTime = 0;

// 核心处理逻辑（就是你刚写好的那套）
async function processQueue() {
    if (isProcessingQueue || resolveQueue.length === 0) return;
    isProcessingQueue = true;

    const { link, callback } = resolveQueue.shift();

    // 1. fetch 解析
    try {
        const resp = await fetch(link.url, { redirect: 'follow' });
        if (resp.url && !resp.url.includes("baidu.com/link") && !resp.url.includes("wappass.baidu.com")) {
            link.url = resp.url;
            return finishTask(callback);
        }
    } catch (e) {}

    // 2. 降级隐藏 Tab 解析
    triggerHiddenTab(link, callback);
}

function triggerHiddenTab(link, callback) {
    const now = Date.now();
    const randomGap = Math.floor(Math.random() * 3000) + 3000;
    let waitTime = Math.max(0, randomGap - (now - lastHiddenTabOpenTime));

    setTimeout(() => {
        lastHiddenTabOpenTime = Date.now();

        chrome.tabs.create({ url: link.url, active: false }, (tab) => {
            const tabId = tab.id;
            let isFinished = false;

            const finishAndClose = (finalUrl) => {
                if (isFinished) return;
                isFinished = true;

                chrome.tabs.onUpdated.removeListener(listener);
                clearTimeout(forceTimeout);
                chrome.tabs.remove(tabId).catch(() => {});

                if (finalUrl && !finalUrl.includes("baidu.com/link") && !finalUrl.includes("wappass.baidu.com")) {
                    link.url = finalUrl;
                } else {
                    console.log(`[解析失败] ${link.url}`);
                }
                finishTask(callback);
            };

            const listener = (updatedTabId, changeInfo, updatedTab) => {
                if (updatedTabId === tabId && changeInfo.status === "complete") {
                    setTimeout(() => {
                        chrome.tabs.get(tabId, (finalTab) => {
                            finishAndClose(finalTab ? finalTab.url : "");
                        });
                    }, 500);
                }
            };

            chrome.tabs.onUpdated.addListener(listener);
            const forceTimeout = setTimeout(() => finishAndClose(""), 5000);
        });
    }, waitTime);
}

function finishTask(callback) {
    callback();
    isProcessingQueue = false;
    processQueue();
}

// ★ 对外暴露的唯一接口
export function resolveUrls(links) {
    const promises = links.map(link => {
        // 只有包含特定标识的才进队列，普通的直接返回
        if (link.url.includes("baidu.com/link?url=")) {
            return new Promise((resolve) => {
                resolveQueue.push({ link, callback: resolve });
                processQueue();
            });
        }
        return Promise.resolve();
    });
    return Promise.all(promises);
}