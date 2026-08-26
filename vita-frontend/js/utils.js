export function countUp(el, target, { duration = 900, decimals = 0, suffix = '' } = {}) {
  if (!el) return;
  const start = performance.now();
  function tick(now) {
    const t = Math.min(1, (now - start) / duration);
    const eased = 1 - Math.pow(1 - t, 3);
    el.textContent = (target * eased).toFixed(decimals) + suffix;
    if (t < 1) requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
}

export function vitalsStatus(metric, value) {
  if (value == null || Number.isNaN(value)) return 'unknown';
  switch (metric) {
    case 'heartRate':
      if (value < 50 || value > 120) return 'red';
      if (value < 60 || value > 100) return 'amber';
      return 'green';
    case 'spo2':
      if (value < 90) return 'red';
      if (value < 95) return 'amber';
      return 'green';
    case 'temperature':
      if (value > 38.0) return 'red';
      if (value < 36.1 || value > 37.5) return 'amber';
      return 'green';
    default: return 'green';
  }
}

export function statusDot(status, customLabel) {
  const label = customLabel ?? ({ green: 'Normal', amber: 'Borderline', red: 'Out of range', unknown: '—' }[status] || '');
  return `<span class="dot dot-${status}"></span><span class="text-xs muted">${label}</span>`;
}

export function computeBmi(weightKg, heightCm) {
  if (!weightKg || !heightCm) return null;
  const heightM = heightCm / 100;
  return weightKg / (heightM * heightM);
}

export function bmiStatus(bmi) {
  if (bmi == null || Number.isNaN(bmi)) return { status: 'unknown', label: '—' };
  if (bmi < 18.5) return { status: 'amber', label: 'Underweight' };
  if (bmi < 25)   return { status: 'green', label: 'Normal' };
  if (bmi < 30)   return { status: 'amber', label: 'Overweight' };
  return { status: 'red', label: 'Obese' };
}

export function formatDate(ts) {
  if (!ts) return '';
  const iso = (typeof ts === 'string' && !ts.endsWith('Z') && !ts.includes('+')) ? ts + 'Z' : ts;
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '';
  return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

export function formatTime(ts) {
  if (!ts) return '';
  const iso = (typeof ts === 'string' && !ts.endsWith('Z') && !ts.includes('+')) ? ts + 'Z' : ts;
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '';
  return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}
export function todayISO() { return new Date().toISOString().slice(0, 10); }

export function toast(msg, type = 'success') {
  let wrap = document.querySelector('.toast-wrap');
  if (!wrap) { wrap = document.createElement('div'); wrap.className = 'toast-wrap'; document.body.appendChild(wrap); }
  const t = document.createElement('div');
  t.className = `toast toast-${type}`;
  t.textContent = msg;
  wrap.appendChild(t);
  setTimeout(() => { t.style.opacity = '0'; t.style.transform = 'translateX(20px)'; }, 2400);
  setTimeout(() => t.remove(), 2700);
}

export function initLucide() { if (window.lucide) window.lucide.createIcons(); }
export function waitForChart(timeout = 350) {
  if (window.Chart) return Promise.resolve(true);
  const started = performance.now();
  return new Promise((resolve) => {
    const tick = () => {
      if (window.Chart) return resolve(true);
      if (performance.now() - started >= timeout) return resolve(false);
      setTimeout(tick, 50);
    };
    tick();
  });
}
export function applyStoredTheme() {
  if (localStorage.getItem('theme') === 'dark') document.documentElement.classList.add('dark');
}
export function toggleTheme() {
  const isDark = document.documentElement.classList.toggle('dark');
  localStorage.setItem('theme', isDark ? 'dark' : 'light');
}
export function initThemeToggle(btnId = 'theme-btn') {
  const btn = document.getElementById(btnId);
  if (btn) btn.addEventListener('click', toggleTheme);
}

export async function compressImage(file, maxDimension = 1200, quality = 0.80) {
  if (!file || !file.type.startsWith('image/')) return file;

  const canvasToBlob = (canvas, q) => {
    return new Promise((resolve) => {
      canvas.toBlob(
        (blob) => {
          if (blob && blob.size > 0) return resolve(blob);
          try {
            const dataUrl = canvas.toDataURL('image/jpeg', q);
            const byteString = atob(dataUrl.split(',')[1]);
            const mimeString = dataUrl.split(',')[0].split(':')[1].split(';')[0];
            const ab = new ArrayBuffer(byteString.length);
            const ia = new Uint8Array(ab);
            for (let i = 0; i < byteString.length; i++) {
              ia[i] = byteString.charCodeAt(i);
            }
            resolve(new Blob([ab], { type: mimeString }));
          } catch {
            resolve(null);
          }
        },
        'image/jpeg',
        q
      );
    });
  };

  try {
    let sourceWidth, sourceHeight, drawSource;
    let cleanup = () => {};

    if (typeof createImageBitmap === 'function') {
      try {
        const bitmap = await createImageBitmap(file);
        sourceWidth = bitmap.width;
        sourceHeight = bitmap.height;
        drawSource = bitmap;
        cleanup = () => bitmap.close();
      } catch {
        // Fall back to Image element if createImageBitmap fails
      }
    }

    if (!drawSource) {
      const img = new Image();
      const url = URL.createObjectURL(file);
      cleanup = () => URL.revokeObjectURL(url);
      await new Promise((resolve, reject) => {
        img.onload = resolve;
        img.onerror = () => reject(new Error('Image load error'));
        img.src = url;
      });
      sourceWidth = img.width;
      sourceHeight = img.height;
      drawSource = img;
    }

    if (sourceWidth <= maxDimension && sourceHeight <= maxDimension && file.size <= 300 * 1024) {
      cleanup();
      return file;
    }

    let targetWidth = sourceWidth;
    let targetHeight = sourceHeight;
    if (sourceWidth > maxDimension || sourceHeight > maxDimension) {
      if (sourceWidth > sourceHeight) {
        targetHeight = Math.round((sourceHeight * maxDimension) / sourceWidth);
        targetWidth = maxDimension;
      } else {
        targetWidth = Math.round((sourceWidth * maxDimension) / sourceHeight);
        targetHeight = maxDimension;
      }
    }

    const canvas = document.createElement('canvas');
    canvas.width = targetWidth;
    canvas.height = targetHeight;
    const ctx = canvas.getContext('2d');
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = 'high';
    ctx.fillStyle = '#FFFFFF';
    ctx.fillRect(0, 0, targetWidth, targetHeight);
    ctx.drawImage(drawSource, 0, 0, targetWidth, targetHeight);
    cleanup();

    let blob = await canvasToBlob(canvas, quality);
    if (blob && blob.size > 800 * 1024) {
      const lowerBlob = await canvasToBlob(canvas, 0.65);
      if (lowerBlob && lowerBlob.size > 0) blob = lowerBlob;
    }

    if (!blob || blob.size === 0) return file;

    const fileName = (file.name || 'photo.jpg').replace(/\.[^/.]+$/, '') + '.jpg';
    return new File([blob], fileName, { type: 'image/jpeg', lastModified: Date.now() });

  } catch (err) {
    console.warn('Image compression fallback:', err);
    return file;
  }
}


