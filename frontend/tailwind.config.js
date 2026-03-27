var config = {
    darkMode: ["class"],
    content: ["./index.html", "./src/**/*.{ts,tsx}"],
    theme: {
        container: {
            center: true,
            padding: "1rem",
            screens: {
                "2xl": "1440px",
            },
        },
        extend: {
            colors: {
                border: "hsl(var(--border))",
                input: "hsl(var(--input))",
                ring: "hsl(var(--ring))",
                background: "hsl(var(--background))",
                foreground: "hsl(var(--foreground))",
                surface: "hsl(var(--surface))",
                brand: {
                    DEFAULT: "hsl(var(--brand))",
                    foreground: "hsl(var(--brand-foreground))",
                },
                success: "hsl(var(--success))",
                warning: "hsl(var(--warning))",
                destructive: "hsl(var(--destructive))",
                muted: {
                    DEFAULT: "hsl(var(--muted))",
                    foreground: "hsl(var(--muted-foreground))",
                },
                card: {
                    DEFAULT: "hsl(var(--card))",
                    foreground: "hsl(var(--card-foreground))",
                },
            },
            borderRadius: {
                sm: "6px",
                md: "8px",
                lg: "12px",
            },
            boxShadow: {
                floating: "0 4px 6px -1px rgb(0 0 0 / 0.1)",
                modal: "0 25px 50px -12px rgb(0 0 0 / 0.25)",
                menu: "0 10px 15px -3px rgb(0 0 0 / 0.1)",
            },
            fontFamily: {
                sans: ['"IBM Plex Sans"', '"Inter Variable"', '"Segoe UI"', "sans-serif"],
                mono: ['"JetBrains Mono"', '"Cascadia Code"', "monospace"],
            },
            keyframes: {
                "fade-in-up": {
                    "0%": { opacity: "0", transform: "translateY(8px)" },
                    "100%": { opacity: "1", transform: "translateY(0)" },
                },
                cursor: {
                    "0%, 100%": { opacity: "0" },
                    "50%": { opacity: "1" },
                },
                pulseRing: {
                    "0%": { transform: "scale(0.95)", opacity: "0.7" },
                    "70%": { transform: "scale(1)", opacity: "1" },
                    "100%": { transform: "scale(0.95)", opacity: "0.7" },
                },
            },
            animation: {
                "fade-in-up": "fade-in-up 150ms ease-out",
                cursor: "cursor 1s infinite",
                pulseRing: "pulseRing 1s ease-out infinite",
            },
        },
    },
    plugins: [],
};
export default config;
