(function() {
    const animatedElements = document.querySelectorAll('[data-animate]');
    if (!animatedElements.length) return;

    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const el = entry.target;
                const animation = el.getAttribute('data-animate');
                const delay = el.getAttribute('data-delay') || '0';
                el.style.transitionDelay = delay + 'ms';
                el.classList.add('animate-' + animation);
                observer.unobserve(el);
            }
        });
    }, { threshold: 0.15, rootMargin: '0px 0px -30px 0px' });

    animatedElements.forEach(el => observer.observe(el));
})();