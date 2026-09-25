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