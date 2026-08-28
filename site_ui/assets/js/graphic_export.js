/**
 * Graphic Export Module for Boardgame Recommender
 * Generates a sleek, high-resolution 1200x675 shareable PNG of the Top 10 recommended games
 * (without AI text) using HTML5 Canvas.
 */

(function() {
    // Helper to draw a rounded rectangle
    function roundRect(ctx, x, y, width, height, radius, fill, stroke) {
        if (typeof radius === 'number') {
            radius = {tl: radius, tr: radius, br: radius, bl: radius};
        } else {
            radius = Object.assign({tl: 0, tr: 0, br: 0, bl: 0}, radius);
        }
        ctx.beginPath();
        ctx.moveTo(x + radius.tl, y);
        ctx.lineTo(x + width - radius.tr, y);
        ctx.quadraticCurveTo(x + width, y, x + width, y + radius.tr);
        ctx.lineTo(x + width, y + height - radius.br);
        ctx.quadraticCurveTo(x + width, y + height, x + width - radius.br, y + height);
        ctx.lineTo(x + radius.bl, y + height);
        ctx.quadraticCurveTo(x, y + height, x, y + height - radius.bl);
        ctx.lineTo(x, y + radius.tl);
        ctx.quadraticCurveTo(x, y, x + radius.tl, y);
        ctx.closePath();
        if (fill) ctx.fill();
        if (stroke) ctx.stroke();
    }

    // Helper to load image safely with CORS proxy and timeout fallback
    function loadImage(rawUrl, timeoutMs = 3500) {
        return new Promise((resolve) => {
            if (!rawUrl || rawUrl.includes('placeholder_thumb')) {
                resolve(null);
                return;
            }

            // Route through wsrv.nl to bypass CDN CORS restrictions when exporting HTML5 canvas
            const proxiedUrl = rawUrl.startsWith('http') 
                ? `https://wsrv.nl/?url=${encodeURIComponent(rawUrl)}&w=250&output=jpg` 
                : rawUrl;

            const img = new Image();
            img.crossOrigin = 'anonymous';
            let timedOut = false;
            const timer = setTimeout(() => {
                timedOut = true;
                resolve(null);
            }, timeoutMs);

            img.onload = () => {
                if (!timedOut) {
                    clearTimeout(timer);
                    resolve(img);
                }
            };
            img.onerror = () => {
                // Fallback to alternate images.weserv.nl if wsrv fails
                if (rawUrl.startsWith('http')) {
                    const fallbackImg = new Image();
                    fallbackImg.crossOrigin = 'anonymous';
                    fallbackImg.onload = () => {
                        if (!timedOut) {
                            clearTimeout(timer);
                            resolve(fallbackImg);
                        }
                    };
                    fallbackImg.onerror = () => {
                        if (!timedOut) {
                            clearTimeout(timer);
                            resolve(null);
                        }
                    };
                    fallbackImg.src = `https://images.weserv.nl/?url=${encodeURIComponent(rawUrl)}&w=250&output=jpg`;
                } else {
                    if (!timedOut) {
                        clearTimeout(timer);
                        resolve(null);
                    }
                }
            };
            img.src = proxiedUrl;
        });
    }

    // Helper to wrap text into max lines
    function wrapText(ctx, text, maxWidth, maxLines = 2) {
        const words = text.split(' ');
        const lines = [];
        let currentLine = words[0] || '';

        for (let i = 1; i < words.length; i++) {
            const word = words[i];
            const width = ctx.measureText(currentLine + ' ' + word).width;
            if (width < maxWidth) {
                currentLine += ' ' + word;
            } else {
                lines.push(currentLine);
                currentLine = word;
                if (lines.length === maxLines - 1) {
                    break;
                }
            }
        }
        if (currentLine && lines.length < maxLines) {
            lines.push(currentLine);
        }

        // If there are more words left and we hit maxLines, append ellipsis
        if (lines.length === maxLines && words.indexOf(currentLine.split(' ').slice(-1)[0]) < words.length - 1) {
            let lastLine = lines[maxLines - 1];
            while (ctx.measureText(lastLine + '…').width > maxWidth && lastLine.length > 0) {
                lastLine = lastLine.substring(0, lastLine.length - 1);
            }
            lines[maxLines - 1] = lastLine + '…';
        }

        return lines;
    }

    // Main graphic generator (Mobile-First 9:16 Vertical Poster: 1080 x 1920)
    window.generateRecommendationGraphic = async function(recs, titleText = "Personalized Recommendations", subtitleText = "") {
        const top10 = (recs || []).slice(0, 10);
        const canvas = document.createElement('canvas');
        canvas.width = 1080;
        canvas.height = 1920;
        const ctx = canvas.getContext('2d');

        // 1. Background Gradient (Deep slate to indigo)
        const bgGrad = ctx.createLinearGradient(0, 0, 1080, 1920);
        bgGrad.addColorStop(0, '#090d16');
        bgGrad.addColorStop(0.5, '#0f172a');
        bgGrad.addColorStop(1, '#1e1b4b');
        ctx.fillStyle = bgGrad;
        ctx.fillRect(0, 0, 1080, 1920);

        // Ambient background glow circles
        ctx.save();
        const glow1 = ctx.createRadialGradient(180, 150, 10, 180, 150, 450);
        glow1.addColorStop(0, 'rgba(99, 102, 241, 0.18)');
        glow1.addColorStop(1, 'rgba(99, 102, 241, 0)');
        ctx.fillStyle = glow1;
        ctx.fillRect(0, 0, 1080, 1920);

        const glow2 = ctx.createRadialGradient(900, 1750, 10, 900, 1750, 500);
        glow2.addColorStop(0, 'rgba(168, 85, 247, 0.18)');
        glow2.addColorStop(1, 'rgba(168, 85, 247, 0)');
        ctx.fillStyle = glow2;
        ctx.fillRect(0, 0, 1080, 1920);
        ctx.restore();

        // 2. Header Section
        ctx.save();
        // Logo / Title
        ctx.font = 'bold 38px "Outfit", "Inter", sans-serif';
        ctx.fillStyle = '#ffffff';
        ctx.fillText('🎲 Boardgame Recommender', 50, 82);

        // Subtitle
        ctx.font = '600 22px "Inter", sans-serif';
        ctx.fillStyle = '#818cf8';
        const displaySubtitle = subtitleText ? `Top 10 Picks for ${subtitleText}` : 'Top 10 Personalized Recommendations';
        ctx.fillText(displaySubtitle, 50, 124);
        ctx.restore();

        // 3. Preload all thumbnails
        const thumbPromises = top10.map(rec => loadImage(rec.thumbnail));
        const loadedImages = await Promise.all(thumbPromises);

        // 4. Render 2x5 Grid of Cards (2 Columns x 5 Rows)
        const cols = 2;
        const rows = 5;
        const startX = 50;
        const startY = 160;
        const cardWidth = 465;
        const cardHeight = 315;
        const gapX = 50;
        const gapY = 24;

        for (let i = 0; i < top10.length; i++) {
            const rec = top10[i];
            const col = i % cols;
            const row = Math.floor(i / cols);
            const x = startX + col * (cardWidth + gapX);
            const y = startY + row * (cardHeight + gapY);

            ctx.save();
            // Card Container (Frosted Glass)
            ctx.fillStyle = 'rgba(30, 41, 59, 0.78)';
            ctx.strokeStyle = 'rgba(255, 255, 255, 0.12)';
            ctx.lineWidth = 1.5;
            roundRect(ctx, x, y, cardWidth, cardHeight, 16, true, true);

            // Match Rank Pill (#1, #2...)
            ctx.fillStyle = 'rgba(99, 102, 241, 0.28)';
            roundRect(ctx, x + 16, y + 16, 52, 28, 14, true, false);
            ctx.font = 'bold 15px "Inter", sans-serif';
            ctx.fillStyle = '#c7d2fe';
            ctx.textAlign = 'center';
            ctx.fillText(`#${i + 1}`, x + 42, y + 35.5);

            // Year Pill (if available)
            if (rec.year_published) {
                ctx.fillStyle = 'rgba(148, 163, 184, 0.18)';
                roundRect(ctx, x + cardWidth - 76, y + 16, 60, 28, 14, true, false);
                ctx.font = '600 14px "Inter", sans-serif';
                ctx.fillStyle = '#94a3b8';
                ctx.textAlign = 'center';
                ctx.fillText(`${rec.year_published}`, x + cardWidth - 46, y + 35.5);
            }

            // Thumbnail (Image or Placeholder) - 125x125
            const imgW = 125;
            const imgH = 125;
            const imgX = x + (cardWidth - imgW) / 2;
            const imgY = y + 38;

            ctx.save();
            roundRect(ctx, imgX, imgY, imgW, imgH, 12, false, false);
            ctx.clip();

            const img = loadedImages[i];
            if (img && img.width > 0 && img.height > 0) {
                const hRatio = imgW / img.width;
                const vRatio = imgH / img.height;
                const ratio = Math.max(hRatio, vRatio);
                const centerShiftX = (imgW - img.width * ratio) / 2;
                const centerShiftY = (imgH - img.height * ratio) / 2;
                ctx.drawImage(img, 0, 0, img.width, img.height,
                    imgX + centerShiftX, imgY + centerShiftY, img.width * ratio, img.height * ratio);
            } else {
                // Fallback gradient placeholder
                const pGrad = ctx.createLinearGradient(imgX, imgY, imgX + imgW, imgY + imgH);
                pGrad.addColorStop(0, '#334155');
                pGrad.addColorStop(1, '#1e293b');
                ctx.fillStyle = pGrad;
                ctx.fillRect(imgX, imgY, imgW, imgH);
                ctx.font = 'bold 36px sans-serif';
                ctx.fillStyle = '#64748b';
                ctx.textAlign = 'center';
                ctx.fillText('🎲', imgX + imgW / 2, imgY + 75);
            }
            ctx.restore();

            // Border around thumbnail
            ctx.strokeStyle = 'rgba(255, 255, 255, 0.18)';
            ctx.lineWidth = 1.5;
            roundRect(ctx, imgX, imgY, imgW, imgH, 12, false, true);

            // Game Title (Symmetrically centered between thumbnail bottom y+163 and stat badges top y+248)
            const titleZoneCenterY = y + 163 + 85 / 2; // y + 205.5
            ctx.fillStyle = '#f8fafc';
            ctx.textAlign = 'center';
            const lines = wrapText(ctx, rec.name || 'Untitled Game', cardWidth - 28, 2);

            if (lines.length === 1) {
                ctx.font = 'bold 18.5px "Inter", sans-serif';
                ctx.fillText(lines[0], x + cardWidth / 2, titleZoneCenterY + 6);
            } else {
                ctx.font = 'bold 16.5px "Inter", sans-serif';
                ctx.fillText(lines[0], x + cardWidth / 2, titleZoneCenterY - 7);
                ctx.fillText(lines[1], x + cardWidth / 2, titleZoneCenterY + 17);
            }

            // Stat Badges Bar (Bottom row inside card) - 4 pills
            const badgeY = y + 254;
            const badgeH = 34;
            const badgeW = 98;
            const badgeGap = 8;
            const badgesStartX = x + (cardWidth - (4 * badgeW + 3 * badgeGap)) / 2;

            // Rating Badge (★)
            const ratingVal = rec.rating ? rec.rating.toFixed(1) : 'N/A';
            ctx.fillStyle = 'rgba(245, 158, 11, 0.18)';
            roundRect(ctx, badgesStartX, badgeY, badgeW, badgeH, 7, true, false);
            ctx.font = 'bold 13px "Inter", sans-serif';
            ctx.fillStyle = '#fde68a';
            ctx.textAlign = 'center';
            ctx.fillText(`★ ${ratingVal}`, badgesStartX + badgeW / 2, badgeY + 22);

            // Complexity Badge (⚙)
            const compVal = rec.complexity ? rec.complexity.toFixed(1) : 'N/A';
            const b2X = badgesStartX + badgeW + badgeGap;
            ctx.fillStyle = 'rgba(168, 85, 247, 0.18)';
            roundRect(ctx, b2X, badgeY, badgeW, badgeH, 7, true, false);
            ctx.fillStyle = '#f5d0fe';
            ctx.fillText(`⚙ ${compVal}`, b2X + badgeW / 2, badgeY + 22);

            // Players Badge (👥)
            const b3X = b2X + badgeW + badgeGap;
            let playerVal = rec.min_players ? (rec.min_players === rec.max_players ? `${rec.min_players}` : `${rec.min_players}-${rec.max_players}`) : 'All';
            if (playerVal.length > 5) playerVal = `${rec.min_players || 1}+`;
            ctx.fillStyle = 'rgba(16, 185, 129, 0.18)';
            roundRect(ctx, b3X, badgeY, badgeW, badgeH, 7, true, false);
            ctx.fillStyle = '#a7f3d0';
            ctx.fillText(`👥 ${playerVal}`, b3X + badgeW / 2, badgeY + 22);

            // Playtime Badge (🕒)
            const b4X = b3X + badgeW + badgeGap;
            let playVal = rec.playing_time ? `${rec.playing_time}m` : (rec.min_playtime ? `${rec.min_playtime}m` : '30m');
            ctx.fillStyle = 'rgba(14, 165, 233, 0.18)';
            roundRect(ctx, b4X, badgeY, badgeW, badgeH, 7, true, false);
            ctx.fillStyle = '#bae6fd';
            ctx.fillText(`🕒 ${playVal}`, b4X + badgeW / 2, badgeY + 22);

            ctx.restore();
        }

        // 5. Footer Branding
        ctx.save();
        ctx.font = '500 16px "Inter", sans-serif';
        ctx.fillStyle = '#64748b';
        ctx.textAlign = 'left';
        ctx.fillText('Find your perfect tabletop games at bionicle4365.github.io/Boardgame-Recommender', 50, 1885);

        ctx.textAlign = 'right';
        ctx.fillText(new Date().toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' }), 1030, 1885);
        ctx.restore();

        // Generate data URL and Blob
        const dataUrl = canvas.toDataURL('image/png');
        const blob = await new Promise(res => canvas.toBlob(res, 'image/png'));

        return {
            canvas,
            dataUrl,
            blob
        };
    };

    // Modal UI Controller
    window.openGraphicExportModal = async function(recs, subtitleContext = "") {
        if (!recs || recs.length === 0) {
            alert('Please generate recommendations before exporting a graphic.');
            return;
        }

        // Ensure modal container exists
        let modalEl = document.getElementById('graphic-export-modal');
        if (!modalEl) {
            modalEl = document.createElement('div');
            modalEl.id = 'graphic-export-modal';
            modalEl.className = 'export-modal-overlay';
            document.body.appendChild(modalEl);
        }

        // Show loading state
        modalEl.innerHTML = `
            <div class="export-modal-dialog">
                <div class="export-modal-header">
                    <h3>🖼️ Export Recommendation Graphic</h3>
                    <button class="export-modal-close" onclick="window.closeGraphicExportModal()">&times;</button>
                </div>
                <div class="export-modal-body" style="text-align: center; padding: 40px 20px;">
                    <div class="spinner" style="margin: 0 auto 16px auto; width: 36px; height: 36px;"></div>
                    <p style="color: var(--text-muted); font-size: 0.95rem;">Rendering high-resolution graphic...</p>
                </div>
            </div>
        `;
        modalEl.style.display = 'flex';

        try {
            const { dataUrl, blob } = await window.generateRecommendationGraphic(recs, "Personalized Recommendations", subtitleContext);

            modalEl.innerHTML = `
                <div class="export-modal-dialog">
                    <div class="export-modal-header">
                        <h3 style="margin: 0;">🖼️ Shareable Recommendation Graphic</h3>
                        <button class="export-modal-close" onclick="window.closeGraphicExportModal()">&times;</button>
                    </div>
                    <div class="export-modal-body">
                        <div class="export-graphic-preview">
                            <img src="${dataUrl}" alt="Top 10 Board Game Recommendations" id="exported-graphic-img">
                        </div>
                        <div class="export-modal-actions">
                            <button type="button" class="btn btn-submit" id="btn-download-graphic">
                                <span>📥 Download PNG</span>
                            </button>
                            <button type="button" class="btn btn-secondary" id="btn-copy-graphic">
                                <span>📋 Copy Image</span>
                            </button>
                            <button type="button" class="btn btn-secondary" id="btn-share-graphic" style="display: none;">
                                <span>📱 Share</span>
                            </button>
                        </div>
                    </div>
                </div>
            `;

            // Download handler
            document.getElementById('btn-download-graphic').onclick = () => {
                const a = document.createElement('a');
                a.download = `boardgame_recommendations_${Date.now()}.png`;
                a.href = dataUrl;
                a.click();
            };

            // Clipboard copy handler
            const copyBtn = document.getElementById('btn-copy-graphic');
            copyBtn.onclick = async () => {
                try {
                    if (navigator.clipboard && window.ClipboardItem) {
                        await navigator.clipboard.write([
                            new ClipboardItem({ 'image/png': blob })
                        ]);
                        copyBtn.querySelector('span').textContent = '✓ Copied to Clipboard!';
                        setTimeout(() => {
                            copyBtn.querySelector('span').textContent = '📋 Copy Image';
                        }, 2500);
                    } else {
                        // Fallback: download directly if clipboard image not supported
                        const a = document.createElement('a');
                        a.download = `boardgame_recommendations.png`;
                        a.href = dataUrl;
                        a.click();
                    }
                } catch (e) {
                    console.warn('Clipboard write error:', e);
                    // Fallback to downloading image
                    const a = document.createElement('a');
                    a.download = `boardgame_recommendations.png`;
                    a.href = dataUrl;
                    a.click();
                }
            };

            // Mobile Web Share API handler
            const shareBtn = document.getElementById('btn-share-graphic');
            if (navigator.canShare && navigator.canShare({ files: [new File([blob], 'recs.png', { type: 'image/png' })] })) {
                shareBtn.style.display = 'inline-flex';
                shareBtn.onclick = async () => {
                    try {
                        const file = new File([blob], 'boardgame_recommendations.png', { type: 'image/png' });
                        await navigator.share({
                            title: 'My Top 10 Board Game Recommendations',
                            text: 'Check out my top board game recommendations generated with AI!',
                            files: [file]
                        });
                    } catch (err) {
                        if (err.name !== 'AbortError') {
                            console.warn('Share error:', err);
                        }
                    }
                };
            }

            // Close on overlay backdrop click
            modalEl.onclick = (e) => {
                if (e.target === modalEl) {
                    window.closeGraphicExportModal();
                }
            };

        } catch (err) {
            console.error('Failed to generate recommendation graphic:', err);
            modalEl.innerHTML = `
                <div class="export-modal-dialog">
                    <div class="export-modal-header">
                        <h3>Error</h3>
                        <button class="export-modal-close" onclick="window.closeGraphicExportModal()">&times;</button>
                    </div>
                    <div class="export-modal-body" style="padding: 30px 20px; text-align: center;">
                        <p style="color: #ef4444;">Failed to generate image graphic. Please try again.</p>
                    </div>
                </div>
            `;
        }
    };

    window.closeGraphicExportModal = function() {
        const modalEl = document.getElementById('graphic-export-modal');
        if (modalEl) {
            modalEl.style.display = 'none';
        }
    };

    // Close on Escape key
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            window.closeGraphicExportModal();
        }
    });

})();
