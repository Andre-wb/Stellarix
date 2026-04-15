// static/js/onboarding.js
// ============================================================================
// Guided onboarding tour for new users.
// Shows a 5-step spotlight + tooltip walkthrough on first launch (0 rooms).
// Persists completion in localStorage so the tour only appears once.
// ============================================================================

const STORAGE_KEY = 'vortex_onboarding_done';

const _tO = (key, fallback) => (typeof window.t === 'function' ? window.t(key) : fallback) || fallback;

const STEPS = [
    {
        target: '#nav-new-room',
        title: () => _tO('onboarding.step1Title', 'Create your first room'),
        text:  () => _tO('onboarding.step1Text', 'Tap here to create a new room and start chatting with others.'),
        position: 'right',
    },
    {
        target: '.header-btn[onclick*="copyInviteCode"]',
        title: () => _tO('onboarding.step2Title', 'Share this code to invite friends'),
        text:  () => _tO('onboarding.step2Text', 'Every room has a unique invite code. Share it so others can join.'),
        position: 'left',
    },
    {
        target: '#msg-input',
        title: () => _tO('onboarding.step3Title', 'Type and send your first message'),
        text:  () => _tO('onboarding.step3Text', 'Write a message and press Enter to send it to the room.'),
        position: 'top',
    },
    {
        target: '#chat-e2e-badge',
        title: () => _tO('onboarding.step4Title', 'All messages are end-to-end encrypted'),
        text:  () => _tO('onboarding.step4Text', 'The lock icon means your conversation is secured. Nobody else can read it.'),
        position: 'left',
    },
    {
        target: null, // completion step — centered, no spotlight
        title: () => _tO('onboarding.step5Title', "You're all set! Enjoy Vortex"),
        text:  () => _tO('onboarding.step5Text', 'You know the basics. Explore rooms, invite friends, and chat securely.'),
        position: 'center',
    },
];

let _overlay = null;
let _tooltip = null;
let _spotlight = null;
let _currentStep = 0;
let _resizeHandler = null;

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Begin the onboarding tour. Safe to call multiple times — will no-op if
 * already dismissed or currently running.
 */
export function startOnboarding() {
    if (localStorage.getItem(STORAGE_KEY)) return;
    if (_overlay) return; // already running
    _currentStep = 0;
    _createOverlay();
    _showStep(_currentStep);
}

/**
 * Returns true when the user has completed or skipped onboarding.
 */
export function isOnboardingDone() {
    return localStorage.getItem(STORAGE_KEY) === '1';
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

function _createOverlay() {
    // Overlay (dark backdrop — the spotlight hole is cut via CSS mask)
    _overlay = document.createElement('div');
    _overlay.className = 'onboarding-overlay';

    // Spotlight ring
    _spotlight = document.createElement('div');
    _spotlight.className = 'onboarding-spotlight';

    // Tooltip
    _tooltip = document.createElement('div');
    _tooltip.className = 'onboarding-tooltip';

    document.body.appendChild(_overlay);
    document.body.appendChild(_spotlight);
    document.body.appendChild(_tooltip);

    // Close tour on overlay click outside the tooltip
    _overlay.addEventListener('click', _handleOverlayClick);

    // Reposition on resize / scroll
    _resizeHandler = () => _positionStep(_currentStep);
    window.addEventListener('resize', _resizeHandler);
    window.addEventListener('scroll', _resizeHandler, true);
}

function _handleOverlayClick(e) {
    if (e.target === _overlay) {
        // clicking the dim overlay skips the tour
        _finish();
    }
}

function _showStep(idx) {
    _currentStep = idx;
    const step = STEPS[idx];
    const isLast = idx === STEPS.length - 1;

    // Build tooltip HTML
    const stepCounter = `<span class="onboarding-step-counter">${idx + 1} / ${STEPS.length}</span>`;
    const titleText = typeof step.title === 'function' ? step.title() : step.title;
    const bodyText  = typeof step.text  === 'function' ? step.text()  : step.text;
    const title = `<div class="onboarding-title">${titleText}</div>`;
    const text = `<div class="onboarding-text">${bodyText}</div>`;
    const nextLabel = isLast ? _tO('onboarding.finish', 'Done') : _tO('onboarding.next', 'Next');
    const buttons = `
        <div class="onboarding-buttons">
            ${!isLast ? `<button class="onboarding-btn onboarding-btn-skip">${_tO('onboarding.skipAll', 'Skip')}</button>` : ''}
            <button class="onboarding-btn onboarding-btn-next">${nextLabel}</button>
        </div>`;
    _tooltip.innerHTML = stepCounter + title + text + buttons;

    // Wire button events
    const nextBtn = _tooltip.querySelector('.onboarding-btn-next');
    const skipBtn = _tooltip.querySelector('.onboarding-btn-skip');
    if (nextBtn) nextBtn.addEventListener('click', _onNext);
    if (skipBtn) skipBtn.addEventListener('click', _finish);

    _positionStep(idx);

    // Animate in
    requestAnimationFrame(() => {
        _overlay.classList.add('active');
        _tooltip.classList.add('active');
        _spotlight.classList.add('active');
    });
}

function _positionStep(idx) {
    const step = STEPS[idx];
    const target = step.target ? document.querySelector(step.target) : null;

    if (target) {
        const rect = target.getBoundingClientRect();
        const pad = 8; // padding around the target

        // Position spotlight
        _spotlight.style.display = '';
        _spotlight.style.left = `${rect.left - pad}px`;
        _spotlight.style.top = `${rect.top - pad}px`;
        _spotlight.style.width = `${rect.width + pad * 2}px`;
        _spotlight.style.height = `${rect.height + pad * 2}px`;

        // Cut a hole in the overlay via CSS mask
        const cx = rect.left + rect.width / 2;
        const cy = rect.top + rect.height / 2;
        const rx = (rect.width / 2) + pad + 4;
        const ry = (rect.height / 2) + pad + 4;
        _overlay.style.setProperty('--spot-cx', `${cx}px`);
        _overlay.style.setProperty('--spot-cy', `${cy}px`);
        _overlay.style.setProperty('--spot-rx', `${rx}px`);
        _overlay.style.setProperty('--spot-ry', `${ry}px`);
        _overlay.classList.remove('no-spotlight');

        // Position tooltip relative to target
        _positionTooltip(rect, step.position);
    } else {
        // No target — center tooltip, hide spotlight
        _spotlight.style.display = 'none';
        _overlay.classList.add('no-spotlight');
        _tooltip.classList.add('center');
        _tooltip.style.left = '50%';
        _tooltip.style.top = '50%';
        _tooltip.style.transform = 'translate(-50%, -50%)';
        // Remove position classes
        _tooltip.classList.remove('pos-top', 'pos-bottom', 'pos-left', 'pos-right');
    }
}

function _positionTooltip(rect, position) {
    const gap = 16; // distance between target and tooltip
    _tooltip.classList.remove('center', 'pos-top', 'pos-bottom', 'pos-left', 'pos-right');
    _tooltip.style.transform = '';

    const ttWidth = Math.min(320, window.innerWidth - 32);
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    _tooltip.style.maxWidth = ttWidth + 'px';

    let left, top;

    switch (position) {
        case 'right':
            left = rect.right + gap;
            top = rect.top + rect.height / 2;
            _tooltip.classList.add('pos-right');
            // Ensure it doesn't overflow viewport
            if (left + ttWidth > vw - 16) {
                left = rect.left - gap - ttWidth;
                _tooltip.classList.remove('pos-right');
                _tooltip.classList.add('pos-left');
            }
            _tooltip.style.left = `${left}px`;
            _tooltip.style.top = `${top}px`;
            _tooltip.style.transform = 'translateY(-50%)';
            break;

        case 'bottom':
            left = rect.left + rect.width / 2;
            top = rect.bottom + gap;
            _tooltip.classList.add('pos-bottom');
            if (top + 180 > vh) {
                top = rect.top - gap;
                _tooltip.classList.remove('pos-bottom');
                _tooltip.classList.add('pos-top');
                _tooltip.style.transform = 'translate(-50%, -100%)';
            } else {
                _tooltip.style.transform = 'translateX(-50%)';
            }
            _tooltip.style.left = `${left}px`;
            _tooltip.style.top = `${top}px`;
            break;

        case 'top':
            left = rect.left + rect.width / 2;
            top = rect.top - gap;
            _tooltip.classList.add('pos-top');
            _tooltip.style.transform = 'translate(-50%, -100%)';
            if (top < 80) {
                top = rect.bottom + gap;
                _tooltip.classList.remove('pos-top');
                _tooltip.classList.add('pos-bottom');
                _tooltip.style.transform = 'translateX(-50%)';
            }
            _tooltip.style.left = `${left}px`;
            _tooltip.style.top = `${top}px`;
            break;

        case 'left':
            left = rect.left - gap - ttWidth;
            top = rect.top + rect.height / 2;
            _tooltip.classList.add('pos-left');
            if (left < 16) {
                left = rect.right + gap;
                _tooltip.classList.remove('pos-left');
                _tooltip.classList.add('pos-right');
            }
            _tooltip.style.left = `${left}px`;
            _tooltip.style.top = `${top}px`;
            _tooltip.style.transform = 'translateY(-50%)';
            break;

        default:
            _tooltip.style.left = '50%';
            _tooltip.style.top = '50%';
            _tooltip.style.transform = 'translate(-50%, -50%)';
            break;
    }

    // Clamp after browser layout (requestAnimationFrame ensures transform is applied)
    requestAnimationFrame(() => {
        const r = _tooltip.getBoundingClientRect();
        // Horizontal clamp
        if (r.right > vw - 12) {
            _tooltip.style.left = `${parseFloat(_tooltip.style.left) - (r.right - vw + 12)}px`;
            _tooltip.style.transform = _tooltip.style.transform.replace('translateX(-50%)', '');
        }
        if (r.left < 12) {
            _tooltip.style.left = `${parseFloat(_tooltip.style.left) + (12 - r.left)}px`;
            _tooltip.style.transform = _tooltip.style.transform.replace('translateX(-50%)', '');
        }
        // Vertical clamp
        const r2 = _tooltip.getBoundingClientRect();
        if (r2.bottom > vh - 12) {
            _tooltip.style.top = `${parseFloat(_tooltip.style.top) - (r2.bottom - vh + 12)}px`;
        }
        if (r2.top < 12) {
            _tooltip.style.top = `${parseFloat(_tooltip.style.top) + (12 - r2.top)}px`;
        }
    });
}

function _onNext() {
    if (_currentStep < STEPS.length - 1) {
        _tooltip.classList.remove('active');
        _spotlight.classList.remove('active');
        setTimeout(() => {
            _showStep(_currentStep + 1);
        }, 250);
    } else {
        _finish();
    }
}

function _finish() {
    localStorage.setItem(STORAGE_KEY, '1');

    // Animate out
    _overlay.classList.remove('active');
    _tooltip.classList.remove('active');
    _spotlight.classList.remove('active');

    setTimeout(() => {
        _overlay?.remove();
        _tooltip?.remove();
        _spotlight?.remove();
        _overlay = null;
        _tooltip = null;
        _spotlight = null;
    }, 350);

    if (_resizeHandler) {
        window.removeEventListener('resize', _resizeHandler);
        window.removeEventListener('scroll', _resizeHandler, true);
        _resizeHandler = null;
    }
}
