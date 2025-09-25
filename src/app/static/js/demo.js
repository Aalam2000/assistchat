// ===== DOM READY =====
document.addEventListener("DOMContentLoaded", () => {

  // ===== DEMO ANIMATION BLOCK =====
  const btn = document.getElementById("start-btn");
  const box = document.getElementById("anim-box");

  if (btn && box) {
    btn.addEventListener("click", () => {
      box.classList.toggle("active");
    });
  }
  // ===== END DEMO ANIMATION BLOCK =====


  // ===== MOBILE MENU BLOCK =====
  const menuToggle = document.getElementById("menuToggle");
  const mainNav = document.getElementById("mainNav");

  if (menuToggle && mainNav) {
    menuToggle.addEventListener("click", () => {
      mainNav.classList.toggle("show");
    });
  }
  // ===== END MOBILE MENU BLOCK =====

});
