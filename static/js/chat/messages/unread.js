// =========================================================================
// Unread divider, jump-to-unread button, scroll-to-bottom arrow
// =========================================================================
import { t } from '../../i18n.js';

let _unreadObserver = null;
let _scrollArrowObserver = null;
let _liveUnreadCount = 0;

/**
 * Inserts the unread divider before the first unread message and shows the
 * jump-to-unread floating button.
 *
 * @param {number} unreadCount - number of unread messages from the end of history
 */
export function insertUnreadDivider(unreadCount) {
    cleanupUnreadDivider();
    if (!unreadCount || unreadCount <= 0) return;

    _liveUnreadCount = unreadCount;

    const container = document.getElementById('messages-container');
    if (!container) return;

    const children = Array.from(container.children);
    const total = children.length;
    if (total === 0) return;

    // The divider goes before the (total - unreadCount)-th child
    const insertBefore = Math.max(0, total - unreadCount);
    const refNode = children[insertBefore] || null;

    // Build divider
    const divider = document.createElement('div');
    divider.className = 'unread-divider';
    divider.id = 'unread-divider';
    const label = unreadCount === 1
        ? t('chat.newMessage1')
        : unreadCount < 5
            ? `${unreadCount} ${t('chat.newMessages2_4')}`
            : `${unreadCount} ${t('chat.newMessages5')}`;
    const span = document.createElement('span');
    span.textContent = label;
    divider.appendChild(span);

    if (refNode) {
        container.insertBefore(divider, refNode);
    } else {
        container.appendChild(divider);
    }

    // Put the divider at the top of the viewport so the user lands on the
    // first unread message, not the newest one. rAF gives the browser a
    // chance to finish laying out the just-appended messages — otherwise
    // offsets may be computed against incomplete layout on slower devices.
    requestAnimationFrame(() => {
        const d = document.getElementById('unread-divider');
        if (!d) return;
        try {
            d.scrollIntoView({ behavior: 'instant', block: 'start' });
        } catch (_) {
            // Old Safari: behavior:'instant' was rejected before ~15.4
            d.scrollIntoView({ block: 'start' });
        }
    });

    // IntersectionObserver: when divider visible, reset live counter
    _unreadObserver = new IntersectionObserver(entries => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                _liveUnreadCount = 0;
                _updateScrollArrow();
            }
        });
    }, { root: container, threshold: 0.1 });

    _unreadObserver.observe(divider);

    // Show scroll arrow with counter
    _updateScrollArrow();
}

/**
 * Called when a new message arrives while the user is scrolled up.
 */
export function incrementLiveUnread() {
    _liveUnreadCount++;
    _updateScrollArrow();
}

/**
 * Removes the unread divider and the jump button. Called on room switch.
 */
export function cleanupUnreadDivider() {
    const divider = document.getElementById('unread-divider');
    if (divider) divider.remove();
    if (_unreadObserver) {
        _unreadObserver.disconnect();
        _unreadObserver = null;
    }
    _liveUnreadCount = 0;
    _removeScrollArrow();
}

/**
 * Scrolls to the unread divider smoothly.
 */
export function jumpToUnread() {
    const divider = document.getElementById('unread-divider');
    if (divider) {
        divider.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
    _liveUnreadCount = 0;
    _updateScrollArrow();
}

// ── Scroll-to-bottom arrow with unread counter ──────────────────────────────

function _updateScrollArrow() {
    let arrow = document.getElementById('scroll-bottom-arrow');
    const chatScreen = document.getElementById('chat-screen');
    if (!chatScreen) return;

    if (!arrow) {
        arrow = document.createElement('div');
        arrow.id = 'scroll-bottom-arrow';
        arrow.className = 'scroll-bottom-arrow';
        arrow.addEventListener('click', () => {
            const container = document.getElementById('messages-container');
            if (container) container.scrollTo({ top: container.scrollHeight, behavior: 'smooth' });
            _liveUnreadCount = 0;
            _updateScrollArrow();
        });

        // Arrow icon (chevron down)
        const svgNS = 'http://www.w3.org/2000/svg';
        const svg = document.createElementNS(svgNS, 'svg');
        svg.setAttribute('width', '20');
        svg.setAttribute('height', '20');
        svg.setAttribute('viewBox', '0 0 24 24');
        svg.setAttribute('fill', 'currentColor');
        const path = document.createElementNS(svgNS, 'path');
        path.setAttribute('d', 'M7.41 8.59L12 13.17l4.59-4.58L18 10l-6 6-6-6z');
        svg.appendChild(path);
        arrow.appendChild(svg);

        // Badge
        const badge = document.createElement('div');
        badge.className = 'scroll-bottom-badge';
        badge.id = 'scroll-bottom-badge';
        arrow.appendChild(badge);

        chatScreen.appendChild(arrow);
    }

    const badge = document.getElementById('scroll-bottom-badge');
    if (_liveUnreadCount > 0) {
        arrow.classList.add('show');
        if (badge) {
            badge.textContent = _liveUnreadCount > 99 ? '99+' : String(_liveUnreadCount);
            badge.style.display = '';
        }
    } else {
        // Still show arrow if scrolled up
        const container = document.getElementById('messages-container');
        if (container) {
            const isAtBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 100;
            if (isAtBottom) {
                arrow.classList.remove('show');
            } else {
                arrow.classList.add('show');
            }
        }
        if (badge) badge.style.display = 'none';
    }
}

function _removeScrollArrow() {
    const arrow = document.getElementById('scroll-bottom-arrow');
    if (arrow) arrow.remove();
}

/**
 * Set up scroll listener on messages container to show/hide arrow.
 */
export function initScrollArrow() {
    const container = document.getElementById('messages-container');
    if (!container) return;
    container.addEventListener('scroll', () => {
        const isAtBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 100;
        if (isAtBottom) {
            _liveUnreadCount = 0;
        }
        _updateScrollArrow();
    });
}

// Expose globally for inline onclick handlers
window.jumpToUnread = jumpToUnread;
