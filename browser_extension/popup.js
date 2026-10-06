chrome.storage.session.get("lastStatus").then(({ lastStatus }) => {
  if (lastStatus) document.getElementById("status").textContent = `${lastStatus.at} - ${lastStatus.text}`;
});
