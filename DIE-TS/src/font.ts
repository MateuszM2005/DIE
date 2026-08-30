export class BitmapFontManager {
    private glyphs: Record<string, HTMLImageElement> = {};
    public loaded = false;

    private neededChars = [
        'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M',
        'N', 'O', 'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z',
        '0', '1', '2', '3', '4', '5', '6', '7', '8', '9'
    ];

    public async loadFont(): Promise<void> {
        console.log("🎬 [Font] Starting the loadFont() procedure...");

        const promises = this.neededChars.map(char => {
            return new Promise<void>((resolve) => {
                const img = new Image();
                img.src = `/static/game/font/${char}.png`;

                img.onload = () => {
                    this.glyphs[char] = img;
                    resolve();
                };

                img.onerror = () => {
                    console.error(`❌ [Font 404] Critical missing file for character: ${char} at path: ${img.src}`);
                    resolve();
                };
            });
        });

        await Promise.all(promises);
        this.loaded = true;
        console.log("✅ [Font] All available glyphs have been processed.");
    }

    public drawString(ctx: CanvasRenderingContext2D, text: string, x: number, y: number, align: 'left' | 'center' | 'right' = 'left', scale = 1.0): void {
        const cleanText = text.toUpperCase();
        if (cleanText.length === 0) return;

        const firstChar = [...cleanText].find(c => this.glyphs[c]);
        if (!firstChar || !this.glyphs[firstChar]) return;

        const baseW = this.glyphs[firstChar].width;
        const charW = baseW * scale;
        const spacing = Math.floor(charW * 0.65);

        // CALCULATING TOTAL WIDTH taking narrower spaces into account
        let totalWidth = 0;
        for (let i = 0; i < cleanText.length; i++) {
            if (cleanText[i] === ' ') {
                totalWidth += Math.floor(spacing * 0.5); // Narrower space in the calculation
            } else {
                totalWidth += (i === cleanText.length - 1) ? charW : spacing;
            }
        }

        let startX = x;
        if (align === 'center') startX = x - totalWidth / 2;
        else if (align === 'right') startX = x - totalWidth;

        // DRAWING
        for (let i = 0; i < cleanText.length; i++) {
            const char = cleanText[i];
            if (char === ' ') {
                startX += Math.floor(spacing * 0.5); // FIXED: The space now has the ideal width
                continue;
            }

            const img = this.glyphs[char];
            if (img) {
                ctx.drawImage(img, startX, y, charW, img.height * scale);
                startX += spacing; // We move the pointer by the standard letter step
            }
        }
    }
}