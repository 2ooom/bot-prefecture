// https://antcpt.com/eng/download/headless-captcha-solving.html
var d = document.getElementById("anticaptcha-imacros-account-key");
if (!d) {
    d = document.createElement("div");
    d.innerHTML = 'anti_captcha_api_key'; // will be replaced by actual value
    d.style.display = "none";
    d.id = "anticaptcha-imacros-account-key";
    document.body.appendChild(d);
}
var s = document.createElement("script");
s.src = "https://cdn.antcpt.com/imacros_inclusion/recaptcha.js?" + Math.random();
document.body.appendChild(s);