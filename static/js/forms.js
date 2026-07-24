document.addEventListener("DOMContentLoaded", () => {
  const dropZone = document.querySelector("#photo-drop-zone");
  const photoInput = dropZone?.querySelector('input[type="file"]');
  const photoPreview = document.querySelector("#photo-preview");

  const showPhoto = (file) => {
    if (!file || !file.type.startsWith("image/")) return;
    const reader = new FileReader();
    reader.addEventListener("load", () => {
      photoPreview.src = reader.result;
      photoPreview.classList.add("visible");
      dropZone.classList.add("has-file");
      dropZone.querySelector("strong").textContent = file.name;
    });
    reader.readAsDataURL(file);
  };

  if (dropZone && photoInput) {
    ["dragenter", "dragover"].forEach((eventName) => {
      dropZone.addEventListener(eventName, (event) => {
        event.preventDefault();
        dropZone.classList.add("dragging");
      });
    });
    ["dragleave", "drop"].forEach((eventName) => {
      dropZone.addEventListener(eventName, (event) => {
        event.preventDefault();
        dropZone.classList.remove("dragging");
      });
    });
    dropZone.addEventListener("drop", (event) => {
      const file = event.dataTransfer.files[0];
      if (!file?.type.startsWith("image/")) return;
      const transfer = new DataTransfer();
      transfer.items.add(file);
      photoInput.files = transfer.files;
      showPhoto(file);
    });
    photoInput.addEventListener("change", () => showPhoto(photoInput.files[0]));
  }

  const orderForm = document.querySelector("#order-form");
  if (orderForm) {
    const packagesContainer = document.querySelector("#packages-container");
    const packageTemplate = document.querySelector("#package-template");
    const lotTemplate = document.querySelector("#lot-template");
    const packageCount = document.querySelector("#package-count");
    const packageDesired = document.querySelector("#package-desired");
    const deletions = document.querySelector("#package-deletions");

    const relabelPackages = () => {
      packagesContainer.querySelectorAll(".package-editor").forEach((card, index) => {
        card.querySelector(".package-label").textContent = index + 1;
      });
      packageDesired.value = packagesContainer.querySelectorAll(".package-editor").length;
    };

    const markDeleted = (name) => {
      const input = document.createElement("input");
      input.type = "hidden";
      input.name = name;
      input.value = "1";
      deletions.appendChild(input);
    };

    const addLot = (packageCard) => {
      const packageIndex = packageCard.dataset.packageIndex;
      const countInput = packageCard.querySelector(".lot-count");
      const lotIndex = Number(countInput.value);
      const html = lotTemplate.innerHTML
        .replaceAll("__P__", packageIndex)
        .replaceAll("__L__", lotIndex);
      packageCard.querySelector(".lot-list").insertAdjacentHTML("beforeend", html);
      countInput.value = lotIndex + 1;
    };

    const addPackage = () => {
      const packageIndex = Number(packageCount.value);
      const html = packageTemplate.innerHTML.replaceAll("__P__", packageIndex);
      packagesContainer.insertAdjacentHTML("beforeend", html);
      packageCount.value = packageIndex + 1;
      const newCard = packagesContainer.querySelector(
        `.package-editor[data-package-index="${packageIndex}"]`
      );
      addLot(newCard);
      relabelPackages();
    };

    packagesContainer.addEventListener("click", (event) => {
      const addButton = event.target.closest(".add-lot");
      if (addButton) {
        addLot(addButton.closest(".package-editor"));
        return;
      }

      const removeLine = event.target.closest(".remove-line");
      if (removeLine) {
        const card = removeLine.closest(".package-editor");
        if (card.querySelectorAll(".lot-row").length <= 1) return;
        const row = removeLine.closest(".lot-row");
        markDeleted(
          `lote-${card.dataset.packageIndex}-${row.dataset.lotIndex}-DELETE`
        );
        row.remove();
        return;
      }

      const removePackage = event.target.closest(".remove-package");
      if (removePackage) {
        if (packagesContainer.querySelectorAll(".package-editor").length <= 1) return;
        const card = removePackage.closest(".package-editor");
        markDeleted(`paquete-${card.dataset.packageIndex}-DELETE`);
        card.remove();
        relabelPackages();
      }
    });

    packageDesired.addEventListener("change", () => {
      const desired = Math.max(1, Math.min(20, Number(packageDesired.value) || 1));
      let cards = [...packagesContainer.querySelectorAll(".package-editor")];
      while (cards.length < desired) {
        addPackage();
        cards = [...packagesContainer.querySelectorAll(".package-editor")];
      }
      while (cards.length > desired) {
        const card = cards.pop();
        markDeleted(`paquete-${card.dataset.packageIndex}-DELETE`);
        card.remove();
      }
      relabelPackages();
    });
    relabelPackages();
  }

  const saleForm = document.querySelector("#sale-form");
  if (saleForm) {
    const lines = document.querySelector("#sale-lines");
    const template = document.querySelector("#sale-line-template");
    const count = document.querySelector("#detail-count");
    const deletions = document.querySelector("#detail-deletions");

    document.querySelector("#add-sale-line").addEventListener("click", () => {
      const index = Number(count.value);
      lines.insertAdjacentHTML(
        "beforeend",
        template.innerHTML.replaceAll("__D__", index)
      );
      count.value = index + 1;
    });

    lines.addEventListener("click", (event) => {
      const button = event.target.closest(".remove-line");
      if (!button || lines.querySelectorAll(".sale-line").length <= 1) return;
      const row = button.closest(".sale-line");
      const input = document.createElement("input");
      input.type = "hidden";
      input.name = `detalle-${row.dataset.detailIndex}-DELETE`;
      input.value = "1";
      deletions.appendChild(input);
      row.remove();
    });
  }
});
