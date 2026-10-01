// External file on purpose: the site CSP is script-src 'self' (no inline JS).

// Toggle optional size inputs dynamically
document.querySelectorAll('input[name^="enable_"]').forEach(function(checkbox) {
  checkbox.addEventListener('change', function() {
    const size = this.name.replace('enable_', '');
    const stockInput = document.getElementById('stock_' + size);
    if (stockInput) {
      stockInput.disabled = !this.checked;
    }
  });
});

// Live image preview
document.querySelectorAll('input[type="file"][data-preview]').forEach(function(input) {
  input.addEventListener('change', function(e) {
    const previewId = this.getAttribute('data-preview');
    const previewImg = document.getElementById(previewId);

    if (e.target.files && e.target.files[0]) {
      const reader = new FileReader();
      reader.onload = function(e) {
        previewImg.src = e.target.result;
        previewImg.style.display = 'block';
      };
      reader.readAsDataURL(e.target.files[0]);
    }
  });
});


// Double-tap confirm for destructive forms (inline confirm() is blocked by CSP)
document.querySelectorAll('form[data-double-tap]').forEach(function (form) {
  const btn = form.querySelector('button[type="submit"]');
  const label = btn.querySelector('span');
  const original = label.textContent;
  let armed = false;
  let timer = null;

  form.addEventListener('submit', function (e) {
    if (armed) return; // second tap → let it submit
    e.preventDefault();
    armed = true;
    label.textContent = form.dataset.confirmText || 'TAP AGAIN TO CONFIRM';
    timer = setTimeout(function () {
      armed = false;
      label.textContent = original;
    }, 5000);
  });
});