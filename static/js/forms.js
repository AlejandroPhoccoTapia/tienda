document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("[data-sale-toggle]").forEach((row) => {
    const toggle = () => {
      const detail = document.querySelector(`#sale-detail-${row.dataset.saleToggle}`);
      const willOpen = detail.hidden;
      detail.hidden = !willOpen;
      row.setAttribute("aria-expanded", String(willOpen));
      row.closest(".sale-card")?.classList.toggle("expanded", willOpen);
    };
    row.addEventListener("click", (event) => {
      if (event.target.closest("button, a, form, input, select, textarea, label")) return;
      toggle();
    });
    row.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        toggle();
      }
    });
  });

  document.querySelectorAll("[data-order-toggle]").forEach((row) => {
    const toggle = () => {
      const detail = document.querySelector(
        `#parcel-detail-${row.dataset.orderToggle}`
      );
      const willOpen = detail.hidden;
      detail.hidden = !willOpen;
      row.setAttribute("aria-expanded", String(willOpen));
      row.closest(".parcel-order")?.classList.toggle("expanded", willOpen);
    };
    row.addEventListener("click", (event) => {
      if (event.target.closest("button, a, form, input, select, textarea, label")) return;
      toggle();
    });
    row.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        toggle();
      }
    });
  });

  document.addEventListener("click", (event) => {
    const opener = event.target.closest("[data-panel-target]");
    if (opener) {
      const panel = document.getElementById(opener.dataset.panelTarget);
      if (panel) {
        panel.hidden = false;
        panel.querySelector("select, input, textarea")?.focus();
        panel.scrollIntoView({ behavior: "smooth", block: "nearest" });
      }
      return;
    }
    const closer = event.target.closest("[data-close-panel]");
    if (closer) {
      const panel = document.getElementById(closer.dataset.closePanel);
      if (panel) panel.hidden = true;
    }
  });

  document.querySelectorAll(".copy-phone").forEach((button) => {
    button.addEventListener("click", async () => {
      const phone = button.dataset.phone;
      let copied = false;
      if (navigator.clipboard && window.isSecureContext) {
        try {
          await navigator.clipboard.writeText(phone);
          copied = true;
        } catch (error) {
          copied = false;
        }
      }
      if (!copied) {
        const temporary = document.createElement("textarea");
        temporary.value = phone;
        temporary.style.position = "fixed";
        temporary.style.opacity = "0";
        document.body.appendChild(temporary);
        temporary.select();
        copied = document.execCommand("copy");
        temporary.remove();
      }
      if (copied) {
        const original = button.textContent;
        button.textContent = "✓";
        button.classList.add("copied");
        window.setTimeout(() => {
          button.textContent = original;
          button.classList.remove("copied");
        }, 1400);
      }
    });
  });

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
    const packagesContainer = document.querySelector("#package-codes-container");
    const productsContainer = document.querySelector("#order-products-container");
    const packageTemplate = document.querySelector("#package-code-template");
    const productTemplate = document.querySelector("#order-product-template");
    const packageCount = document.querySelector("#package-count");
    const productCount = document.querySelector("#order-product-count");
    const packageDeletions = document.querySelector("#package-deletions");
    const productDeletions = document.querySelector("#order-product-deletions");

    const markDeleted = (name, container) => {
      const input = document.createElement("input");
      input.type = "hidden";
      input.name = name;
      input.value = "1";
      container.appendChild(input);
    };

    const addPackage = () => {
      const packageIndex = Number(packageCount.value);
      const html = packageTemplate.innerHTML.replaceAll("__P__", packageIndex);
      packagesContainer.insertAdjacentHTML("beforeend", html);
      packageCount.value = packageIndex + 1;
    };

    const updateReceivedLimit = (row) => {
      const ordered = row.querySelector('input[name$="-cantidad_inicial"]');
      const received = row.querySelector('input[name$="-cantidad_recibida"]');
      if (!ordered || !received) return;
      const maximum = Math.max(0, Number(ordered.value) || 0);
      received.max = maximum;
    };

    const addProduct = () => {
      const productIndex = Number(productCount.value);
      productsContainer.insertAdjacentHTML(
        "beforeend",
        productTemplate.innerHTML.replaceAll("__I__", productIndex)
      );
      productCount.value = productIndex + 1;
      updateReceivedLimit(
        productsContainer.querySelector(
          `.order-product-line[data-product-index="${productIndex}"]`
        )
      );
    };

    document.querySelector("#add-package-code").addEventListener("click", addPackage);
    document.querySelector("#add-order-product").addEventListener("click", addProduct);

    packagesContainer.addEventListener("click", (event) => {
      const button = event.target.closest(".remove-package-code");
      if (!button || packagesContainer.children.length <= 1) return;
      const row = button.closest(".tracking-code-row");
      markDeleted(
        `paquete-${row.dataset.packageIndex}-DELETE`,
        packageDeletions
      );
      row.remove();
    });

    productsContainer.addEventListener("click", (event) => {
      const button = event.target.closest(".remove-order-product");
      if (!button || productsContainer.children.length <= 1) return;
      const row = button.closest(".order-product-line");
      markDeleted(
        `producto-${row.dataset.productIndex}-DELETE`,
        productDeletions
      );
      row.remove();
    });
    productsContainer.addEventListener("input", (event) => {
      if (event.target.matches('input[name$="-cantidad_inicial"]')) {
        updateReceivedLimit(event.target.closest(".order-product-line"));
      }
    });
    productsContainer.querySelectorAll(".order-product-line").forEach(updateReceivedLimit);
  }

  const saleForm = document.querySelector("#sale-form");
  if (saleForm) {
    const lines = document.querySelector("#sale-lines");
    const template = document.querySelector("#sale-line-template");
    const count = document.querySelector("#detail-count");
    const deletions = document.querySelector("#detail-deletions");

    const updateLotLimit = (row) => {
      const select = row.querySelector('select[name$="-inventario_lote"]');
      const quantity = row.querySelector('input[name$="-cantidad"]');
      const price = row.querySelector('input[name$="-precio_unitario_venta"]');
      const commission = row.querySelector('input[name$="-comision_karen"]');
      const hint = row.querySelector(".lot-stock-hint");
      const option = select?.selectedOptions[0];
      const stock = Number(option?.dataset.stock);
      const cost = Number(option?.dataset.cost);
      if (option?.value && Number.isFinite(stock) && Number.isFinite(cost)) {
        const units = Math.max(1, Number(quantity?.value) || 1);
        const karen = Math.max(0, Number(commission?.value) || 0);
        const minimum = Math.ceil((cost + karen / units) * 100) / 100;
        quantity.max = stock;
        price.min = minimum.toFixed(2);
        hint.textContent = `Costo S/${option.dataset.cost} · Stock ${stock} · Mín. S/${minimum.toFixed(2)} c/u`;
      } else {
        quantity.removeAttribute("max");
        price?.removeAttribute("min");
        hint.textContent = "Selecciona un producto para ver costo y stock.";
      }
    };

    document.querySelector("#add-sale-line").addEventListener("click", () => {
      const index = Number(count.value);
      lines.insertAdjacentHTML(
        "beforeend",
        template.innerHTML.replaceAll("__D__", index)
      );
      count.value = index + 1;
      updateLotLimit(lines.querySelector(`.sale-line[data-detail-index="${index}"]`));
    });

    lines.addEventListener("change", (event) => {
      if (event.target.matches('select[name$="-inventario_lote"]')) {
        updateLotLimit(event.target.closest(".sale-line"));
      }
    });
    lines.addEventListener("input", (event) => {
      if (
        event.target.matches(
          'input[name$="-cantidad"], input[name$="-comision_karen"]'
        )
      ) {
        updateLotLimit(event.target.closest(".sale-line"));
      }
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

    lines.querySelectorAll(".sale-line").forEach(updateLotLimit);
  }

  const updateInlineLotLimit = (form) => {
    const select = form.querySelector('select[name$="-inventario_lote"]');
    const quantity = form.querySelector('input[name$="-cantidad"]');
    const price = form.querySelector('input[name$="-precio_unitario_venta"]');
    const commission = form.querySelector('input[name$="-comision_karen"]');
    const hint = form.querySelector(".lot-stock-hint");
    const option = select?.selectedOptions[0];
    const stock = Number(option?.dataset.stock);
    const cost = Number(option?.dataset.cost);
    if (!quantity || !hint) return;
    if (option?.value && Number.isFinite(stock) && Number.isFinite(cost)) {
      const units = Math.max(1, Number(quantity.value) || 1);
      const karen = Math.max(0, Number(commission?.value) || 0);
      const minimum = Math.ceil((cost + karen / units) * 100) / 100;
      quantity.max = stock;
      price.min = minimum.toFixed(2);
      hint.textContent = `Costo S/${option.dataset.cost} · Stock ${stock} · Mín. S/${minimum.toFixed(2)} c/u`;
    } else {
      quantity.removeAttribute("max");
      price?.removeAttribute("min");
    }
  };

  document.querySelectorAll(".product-inline-form").forEach((form) => {
    updateInlineLotLimit(form);
    form.addEventListener("change", (event) => {
      if (event.target.matches('select[name$="-inventario_lote"]')) {
        updateInlineLotLimit(form);
      }
    });
    form.addEventListener("input", (event) => {
      if (
        event.target.matches(
          'input[name$="-cantidad"], input[name$="-comision_karen"]'
        )
      ) {
        updateInlineLotLimit(form);
      }
    });
  });
});
