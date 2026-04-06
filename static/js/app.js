// Custom JavaScript for AI Symptom Checker Demo
document.addEventListener('DOMContentLoaded', function() {
    const i18n = window.APP_I18N || {
        requiredAlert: 'Please fill in all required fields.',
        analyzeBtn: 'Analyze symptoms',
        loadingBtn: 'Analyzing...',
        retryBtn: 'Try again',
        timeoutAlert: 'The response took longer than expected. Please try again.'
    };
    // Symptom chip selection
    const symptomChips = document.querySelectorAll('.symptom-chip');
    const symptomTextarea = document.getElementById('symptoms');

    symptomChips.forEach(chip => {
        chip.addEventListener('click', function() {
            this.classList.toggle('selected');
            updateTextarea();
        });
    });

    function updateTextarea() {
        const selectedChips = document.querySelectorAll('.symptom-chip.selected');
        const symptoms = Array.from(selectedChips).map(chip => chip.textContent.trim());
        if (symptomTextarea) {
            const currentValue = symptomTextarea.value.trim();
            const combined = [...new Set([...currentValue.split(',').map(s => s.trim()).filter(s => s), ...symptoms])];
            symptomTextarea.value = combined.join(', ');
        }
    }

    // Shakl validatsiyasi
    const forms = document.querySelectorAll('form');
    forms.forEach(form => {
        form.addEventListener('submit', function(e) {
            const requiredFields = form.querySelectorAll('[required]');
            let isValid = true;

            requiredFields.forEach(field => {
                if (!field.value.trim()) {
                    field.classList.add('is-invalid');
                    isValid = false;
                } else {
                    field.classList.remove('is-invalid');
                }
            });

            if (!isValid) {
                e.preventDefault();
                alert(i18n.requiredAlert);
                const submitButton = form.querySelector('button[type="submit"]');
                if (submitButton) {
                    submitButton.innerHTML = `<i class="fas fa-brain"></i> ${i18n.analyzeBtn}`;
                    submitButton.disabled = false;
                }
                return;
            }

            const submitButton = form.querySelector('button[type="submit"]');
            if (submitButton) {
                submitButton.innerHTML = `<i class="fas fa-spinner fa-spin"></i> ${i18n.loadingBtn}`;
                submitButton.disabled = true;

                // Agar sahifa o'zgarmasa, foydalanuvchini osilib qolgan holatda qoldirmaymiz.
                window.setTimeout(() => {
                    if (document.body.contains(submitButton) && submitButton.disabled) {
                        submitButton.innerHTML = `<i class="fas fa-rotate-right"></i> ${i18n.retryBtn}`;
                        submitButton.disabled = false;
                        alert(i18n.timeoutAlert);
                    }
                }, 12000);
            }
        });
    });

    // Yosh slayderi
    const ageSlider = document.getElementById('age');
    const ageValue = document.getElementById('age-value');
    if (ageSlider && ageValue) {
        ageSlider.addEventListener('input', function() {
            ageValue.textContent = this.value;
        });
    }

    // Anchor havolalar uchun silliq skroll
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            e.preventDefault();
            const target = document.querySelector(this.getAttribute('href'));
            if (target) {
                target.scrollIntoView({
                    behavior: 'smooth',
                    block: 'start'
                });
            }
        });
    });

    // Favqulodda ogohlantirish animatsiyasi
    const emergencyBanner = document.querySelector('.emergency-banner');
    if (emergencyBanner) {
        setInterval(() => {
            emergencyBanner.style.boxShadow = '0 0 20px rgba(239, 68, 68, 0.3)';
            setTimeout(() => {
                emergencyBanner.style.boxShadow = 'var(--shadow-medium)';
            }, 1000);
        }, 3000);
    }

});
