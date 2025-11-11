document.addEventListener("DOMContentLoaded", function() {
  const decision = document.getElementById("decisionSelect");
  const rejection = document.getElementById("rejectionField");
  decision.addEventListener("change", function() {
    rejection.style.display = this.value === "Nein" ? "block" : "none";
  });
});
