const downloadButton = document.querySelector('.download-panel .button.primary');
if (downloadButton && downloadButton.classList.contains('disabled')) {
  downloadButton.addEventListener('click', (event) => event.preventDefault());
}

const copyCommandButton = document.querySelector('.copy-command-button');
if (copyCommandButton) {
  copyCommandButton.addEventListener('click', async () => {
    const value = copyCommandButton.getAttribute('data-copy') || '';
    if (!value) return;
    try {
      await navigator.clipboard.writeText(value);
      const original = copyCommandButton.textContent;
      copyCommandButton.textContent = 'Copied';
      window.setTimeout(() => {
        copyCommandButton.textContent = original;
      }, 1400);
    } catch (error) {
      window.prompt('Copy this command:', value);
    }
  });
}
