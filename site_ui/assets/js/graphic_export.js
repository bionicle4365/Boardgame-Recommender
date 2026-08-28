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

    // Helper to load image safely with crossOrigin and timeout fallback
    function loadImage(url, timeoutMs = 2500) {
        return new Promise((resolve) => {
            if (!url || url.includes('placeholder_thumb')) {
                resolve(null);
                return;
            }
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
                if (!timedOut) {
                    clearTimeout(timer);
                    resolve(null);
                }
            };
            img.src = url;
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

    // Main graphic generator
    window.generateRecommendationGraphic = async function(recs, titleText = "Personalized Recommendations", subtitleText = "") {
        const top10 = (recs || []).slice(0, 10);
        const canvas = document.createElement('canvas');
        canvas.width = 1200;
        canvas.height = 675;
        const ctx = canvas.getContext('2d');

        // 1. Background Gradient (Deep slate to indigo)
        const bgGrad = ctx.createLinearGradient(0, 0, 1200, 675);
        bgGrad.addColorStop(0, '#090d16');
        bgGrad.addColorStop(0.5, '#0f172a');
        bgGrad.addColorStop(1, '#1e1b4b');
        ctx.fillStyle = bgGrad;
        ctx.fillRect(0, 0, 1200, 675);

        // Subtle ambient background glow circles
        ctx.save();
        const glow1 = ctx.createRadialGradient(150, 100, 10, 150, 100, 300);
        glow1.addColorStop(0, 'rgba(99, 102, 241, 0.15)');
        glow1.addColorStop(1, 'rgba(99, 102, 241, 0)');
        ctx.fillStyle = glow1;
        ctx.fillRect(0, 0, 1200, 675);

        const glow2 = ctx.createRadialGradient(1050, 550, 10, 1050, 550, 350);
        glow2.addColorStop(0, 'rgba(168, 85, 247, 0.15)');
        glow2.addColorStop(1, 'rgba(168, 85, 247, 0)');
        ctx.fillStyle = glow2;
        ctx.fillRect(0, 0, 1200, 675);
        ctx.restore();

        // 2. Header Section
        ctx.save();
        // Logo / Title
        ctx.font = 'bold 26px "Outfit", "Inter", sans-serif';
        ctx.fillStyle = '#ffffff';
        ctx.fillText('🎲 Boardgame Recommender', 48, 48);

        // Subtitle
        ctx.font = '600 15px "Inter", sans-serif';
        ctx.fillStyle = '#818cf8';
        const displaySubtitle = subtitleText ? `Top 10 Picks for ${subtitleText}` : 'Top 10 Personalized Picks';
        ctx.fillText(displaySubtitle, 48, 72);

        // Header Accent Badge on right
        ctx.font = 'bold 12px "Inter", sans-serif';
        ctx.fillStyle = 'rgba(99, 102, 241, 0.2)';
        roundRect(ctx, 1010, 28, 142, 28, 14, true, false);
        ctx.fillStyle = '#a5b4fc';
        ctx.textAlign = 'center';
        ctx.fillText('AI DISCOVERY', 1081, 46);
        ctx.restore();

        // 3. Preload all thumbnails
        const thumbPromises = top10.map(rec => loadImage(rec.thumbnail));
        const loadedImages = await Promise.all(thumbPromises);

        // 4. Render 2x5 Grid of Cards
        // Layout params:
        const cols = 5;
        const rows = 2;
        const startX = 48;
        const startY = 96;
        const cardWidth = 206;
        const cardHeight = 250;
        const gapX = 18;
        const gapY = 16;

        for (let i = 0; i < top10.length; i++) {
            const rec = top10[i];
            const col = i % cols;
            const row = Math.floor(i / cols);
            const x = startX + col * (cardWidth + gapX);
            const y = startY + row * (cardHeight + gapY);

            ctx.save();
            // Card Container (Frosted Glass)
            ctx.fillStyle = 'rgba(30, 41, 59, 0.75)';
            ctx.strokeStyle = 'rgba(255, 255, 255, 0.1)';
            ctx.lineWidth = 1;
            roundRect(ctx, x, y, cardWidth, cardHeight, 12, true, true);

            // Match Rank Pill (#1, #2...)
            ctx.fillStyle = 'rgba(99, 102, 241, 0.25)';
            roundRect(ctx, x + 8, y + 8, 30, 18, 9, true, false);
            ctx.font = 'bold 10px "Inter", sans-serif';
            ctx.fillStyle = '#c7d2fe';
            ctx.textAlign = 'center';
            ctx.fillText(`#${i + 1}`, x + 23, y + 21);

            // Year Pill (if available)
            if (rec.year_published) {
                ctx.fillStyle = 'rgba(148, 163, 184, 0.15)';
                roundRect(ctx, x + cardWidth - 44, y + 8, 36, 18, 9, true, false);
                ctx.font = '600 10px "Inter", sans-serif';
                ctx.fillStyle = '#94a3b8';
                ctx.textAlign = 'center';
                ctx.fillText(`${rec.year_published}`, x + cardWidth - 26, y + 21);
            }

            // Thumbnail (Image or Placeholder)
            const imgW = 90;
            const imgH = 90;
            const imgX = x + (cardWidth - imgW) / 2;
            const imgY = y + 32;

            ctx.save();
            roundRect(ctx, imgX, imgY, imgW, imgH, 8, false, false);
            ctx.clip();

            const img = loadedImages[i];
            if (img) {
                ctx.drawImage(img, imgX, imgY, imgW, imgH);
            } else {
                // Fallback gradient placeholder
                const pGrad = ctx.createLinearGradient(imgX, imgY, imgX + imgW, imgY + imgH);
                pGrad.addColorStop(0, '#334155');
                pGrad.addColorStop(1, '#1e293b');
                ctx.fillStyle = pGrad;
                ctx.fillRect(imgX, imgY, imgW, imgH);
                ctx.font = 'bold 28px sans-serif';
                ctx.fillStyle = '#64748b';
                ctx.textAlign = 'center';
                ctx.fillText('🎲', imgX + imgW / 2, imgY + 55);
            }
            ctx.restore();

            // Border around thumbnail
            ctx.strokeStyle = 'rgba(255, 255, 255, 0.15)';
            ctx.lineWidth = 1;
            roundRect(ctx, imgX, imgY, imgW, imgH, 8, false, true);

            // Game Title
            ctx.font = 'bold 12.5px "Inter", sans-serif';
            ctx.fillStyle = '#f8fafc';
            ctx.textAlign = 'center';
            const lines = wrapText(ctx, rec.name || 'Untitled Game', cardWidth - 20, 2);
            if (lines.length === 1) {
                ctx.fillText(lines[0], x + cardWidth / 2, y + 140);
            } else {
                ctx.fillText(lines[0], x + cardWidth / 2, y + 134);
                ctx.fillText(lines[1], x + cardWidth / 2, y + 149);
            }

            // Stat Badges Bar (Bottom row inside card)
            const badgeY = y + 195;
            const badgeH = 22;
            const badgeW = 41;
            const badgeGap = 4;
            const badgesStartX = x + 12;

            // Rating Badge (★)
            const ratingVal = rec.rating ? rec.rating.toFixed(1) : 'N/A';
            ctx.fillStyle = 'rgba(245, 158, 11, 0.15)';
            roundRect(ctx, badgesStartX, badgeY, badgeW, badgeH, 5, true, false);
            ctx.font = 'bold 10px "Inter", sans-serif';
            ctx.fillStyle = '#fde68a';
            ctx.textAlign = 'center';
            ctx.fillText(`★${ratingVal}`, badgesStartX + badgeW / 2, badgeY + 15);

            // Complexity Badge (⚙)
            const compVal = rec.complexity ? rec.complexity.toFixed(1) : 'N/A';
            const b2X = badgesStartX + badgeW + badgeGap;
            ctx.fillStyle = 'rgba(168, 85, 247, 0.15)';
            roundRect(ctx, b2X, badgeY, badgeW, badgeH, 5, true, false);
            ctx.fillStyle = '#f5d0fe';
            ctx.fillText(`⚙${compVal}`, b2X + badgeW / 2, badgeY + 15);

            // Players Badge (👥)
            const b3X = b2X + badgeW + badgeGap;
            let playerVal = rec.min_players ? (rec.min_players === rec.max_players ? `${rec.min_players}` : `${rec.min_players}-${rec.max_players}`) : 'All';
            if (playerVal.length > 4) playerVal = `${rec.min_players || 1}+`;
            ctx.fillStyle = 'rgba(16, 185, 129, 0.15)';
            roundRect(ctx, b3X, badgeY, badgeW, badgeH, 5, true, false);
            ctx.fillStyle = '#a7f3d0';
            ctx.fillText(`👥${playerVal}`, b3X + badgeW / 2, badgeY + 15);

            // Playtime Badge (🕒)
            const b4X = b3X + badgeW + badgeGap;
            let playVal = rec.playing_time ? `${rec.playing_time}m` : (rec.min_playtime ? `${rec.min_playtime}m` : '30m');
            ctx.fillStyle = 'rgba(14, 165, 233, 0.15)';
            roundRect(ctx, b4X, badgeY, badgeW, badgeH, 5, true, false);
            ctx.fillStyle = '#bae6fd';
            ctx.fillText(`🕒${playVal}`, b4X + badgeW / 2, badgeY + 15);

            ctx.restore();
        }

        // 5. Footer Branding
        ctx.save();
        ctx.font = '500 12px "Inter", sans-serif';
        ctx.fillStyle = '#64748b';
        ctx.textAlign = 'left';
        ctx.fillText('Find your perfect tabletop games at boardgamerecommender.com', 48, 648);

        ctx.textAlign = 'right';
        ctx.fillText(new Date().toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' }), 1152, 648);
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
                        <div>
                            <h3 style="margin: 0 0 2px 0;">🖼️ Shareable Recommendation Card</h3>
                            <p style="margin: 0; font-size: 0.82rem; color: var(--text-muted);">Compact image of your Top 10 recommendations without AI text — perfect for Discord & Reddit</p>
                        </div>
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
