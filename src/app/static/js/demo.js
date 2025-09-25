document.addEventListener("DOMContentLoaded", () => {
  const btn = document.getElementById("start-btn");
  const box = document.getElementById("anim-box");

  btn.addEventListener("click", () => {
    box.classList.toggle("active");
  });
});
