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
    menuToggle.addEventListener("click", (e) => {
      e.preventDefault(); // защита от странных кликов
      mainNav.classList.toggle("show");
      console.log("menu toggle clicked"); // проверка в консоли
    });

    // закрывать меню при клике по ссылке
    mainNav.querySelectorAll("a").forEach(link => {
      link.addEventListener("click", () => {
        mainNav.classList.remove("show");
      });
    });
  }
  // ===== END MOBILE MENU BLOCK =====

});
