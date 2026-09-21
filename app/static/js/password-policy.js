(function () {
  var rules = {
    length: function (v) { return v.length >= 10; },
    lower:  function (v) { return /[a-z]/.test(v); },
    upper:  function (v) { return /[A-Z]/.test(v); },
    digit:  function (v) { return /\d/.test(v); },
    symbol: function (v) { return /[^A-Za-z0-9]/.test(v); }
  };

  document.querySelectorAll('input[data-password-policy]').forEach(function (input) {
    var list = document.getElementById(input.dataset.policyList);
    if (!list) return;

    function check() {
      var allOk = true;
      list.querySelectorAll('li[data-rule]').forEach(function (li) {
        var ok = rules[li.dataset.rule](input.value);
        li.classList.toggle('ok', ok);
        if (!ok) allOk = false;
      });
      input.setCustomValidity(allOk ? '' : 'Password does not meet all requirements.');
    }

    input.addEventListener('input', check);
    check();
  });
})();