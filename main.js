const downloadButton = document.querySelector('.download-panel .button.primary');
if (downloadButton && downloadButton.classList.contains('disabled')) {
  downloadButton.addEventListener('click', (event) => event.preventDefault());
}
