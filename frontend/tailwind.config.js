/** @type {import('tailwindcss').Config} */

// Escalas harmonizadas com a identidade "Premium SaaS". As famílias usadas directamente nas
// páginas (slate, indigo, blue, emerald/green, red, amber, orange, sky, purple, violet) passam a
// derivar da paleta aprovada, para que todos os ecrãs partilhem a mesma semântica de cor.
const neutral = {
  50: '#F2F5F5', 100: '#E8EEEF', 200: '#D2DDE0', 300: '#B5C4C8', 400: '#8FA2A8',
  500: '#5E747B', 600: '#52676E', 700: '#3A4F56', 800: '#243C44', 900: '#132E36', 950: '#0A1619',
};
const petrol = {
  50: '#EEF6F7', 100: '#E4EFF1', 200: '#C5DEE2', 300: '#9CC6CE', 400: '#5FA7B4',
  500: '#2C8291', 600: '#0C5968', 700: '#084451', 800: '#06343E', 900: '#05282F', 950: '#031A1F',
};
const info = {
  50: '#EAF0F5', 100: '#DCE6EF', 200: '#BCD0E0', 300: '#95B3CB', 400: '#7FA5C4',
  500: '#4A7697', 600: '#355D78', 700: '#2B4C63', 800: '#223C4F', 900: '#1A2E3D', 950: '#121F29',
};
const success = {
  50: '#EEF5F0', 100: '#E1EEE5', 200: '#B9D7C4', 300: '#8CC2A1', 400: '#6BAA83',
  500: '#3B7F57', 600: '#2E6E4F', 700: '#286047', 800: '#1E4A37', 900: '#163829', 950: '#0E241B',
};
const danger = {
  50: '#FCECEC', 100: '#F8DEDE', 200: '#F0BDBD', 300: '#E59999', 400: '#E07474',
  500: '#C94646', 600: '#A23131', 700: '#882828', 800: '#6E2020', 900: '#561A1A', 950: '#3A1111',
};
const warning = {
  50: '#FFF7E8', 100: '#FFF2D9', 200: '#FBE0AE', 300: '#F2C675', 400: '#E5A93E',
  500: '#C98A1F', 600: '#A26A12', 700: '#80520F', 800: '#66410C', 900: '#4D310A', 950: '#2E1D06',
};
const stale = {
  50: '#FDF3EB', 100: '#FBE8D9', 200: '#F5CCAB', 300: '#ECAB7A', 400: '#E08A4C',
  500: '#C46A2C', 600: '#A4541D', 700: '#874414', 800: '#6B3610', 900: '#52290A', 950: '#331905',
};
const teal = {
  50: '#EDF7F8', 100: '#DCEFF2', 200: '#B7DEE4', 300: '#8AC8D2', 400: '#5DB0BF',
  500: '#3A93A3', 600: '#2A7584', 700: '#235F6B', 800: '#1D4C56', 900: '#173D45', 950: '#0E272D',
};
const plum = {
  50: '#F4F2F8', 100: '#ECE8F4', 200: '#D8D0E8', 300: '#BBAED6', 400: '#9C8BC2',
  500: '#7B67A8', 600: '#64528F', 700: '#514374', 800: '#40355C', 900: '#312947', 950: '#1F1A2D',
};

module.exports = {
    darkMode: ["class"],
    content: [
    "./src/**/*.{js,jsx,ts,tsx}",
    "./index.html"
  ],
  theme: {
  	extend: {
  		fontFamily: {
  			sans: ['Manrope', '"Segoe UI"', 'system-ui', '-apple-system', 'BlinkMacSystemFont', 'Roboto', 'sans-serif'],
  			// Sem monoespaçada na interface: preços, datas e códigos usam Manrope com algarismos tabulares.
  			mono: ['Manrope', '"Segoe UI"', 'system-ui', '-apple-system', 'sans-serif'],
  		},
  		borderRadius: {
  			lg: 'var(--radius)',
  			md: 'calc(var(--radius) - 1px)',
  			sm: 'calc(var(--radius) - 2px)',
  			xl: 'calc(var(--radius) + 2px)'
  		},
  		boxShadow: {
  			panel: 'var(--shadow-panel)',
  			overlay: 'var(--shadow-overlay)',
  			modal: 'var(--shadow-modal)'
  		},
  		colors: {
  			slate: neutral,
  			gray: neutral,
  			zinc: neutral,
  			indigo: petrol,
  			blue: info,
  			sky: teal,
  			cyan: teal,
  			emerald: success,
  			green: success,
  			red: danger,
  			amber: warning,
  			yellow: warning,
  			orange: stale,
  			purple: plum,
  			violet: plum,
  			background: 'hsl(var(--background))',
  			foreground: 'hsl(var(--foreground))',
  			card: {
  				DEFAULT: 'hsl(var(--card))',
  				foreground: 'hsl(var(--card-foreground))'
  			},
  			popover: {
  				DEFAULT: 'hsl(var(--popover))',
  				foreground: 'hsl(var(--popover-foreground))'
  			},
  			primary: {
  				DEFAULT: 'hsl(var(--primary))',
  				hover: 'hsl(var(--primary-hover))',
  				foreground: 'hsl(var(--primary-foreground))'
  			},
  			secondary: {
  				DEFAULT: 'hsl(var(--secondary))',
  				foreground: 'hsl(var(--secondary-foreground))'
  			},
  			muted: {
  				DEFAULT: 'hsl(var(--muted))',
  				foreground: 'hsl(var(--muted-foreground))'
  			},
  			accent: {
  				DEFAULT: 'hsl(var(--accent))',
  				foreground: 'hsl(var(--accent-foreground))'
  			},
  			destructive: {
  				DEFAULT: 'hsl(var(--destructive))',
  				foreground: 'hsl(var(--destructive-foreground))'
  			},
  			sidebar: {
  				DEFAULT: 'hsl(var(--sidebar))',
  				foreground: 'hsl(var(--sidebar-foreground))',
  				muted: 'hsl(var(--sidebar-muted))',
  				accent: 'hsl(var(--sidebar-accent))',
  				'accent-foreground': 'hsl(var(--sidebar-accent-foreground))',
  				hover: 'hsl(var(--sidebar-hover))',
  				border: 'hsl(var(--sidebar-border))'
  			},
  			success: {
  				DEFAULT: 'hsl(var(--success))',
  				subtle: 'hsl(var(--success-subtle))'
  			},
  			warning: {
  				DEFAULT: 'hsl(var(--warning))',
  				subtle: 'hsl(var(--warning-subtle))'
  			},
  			info: {
  				DEFAULT: 'hsl(var(--info))',
  				subtle: 'hsl(var(--info-subtle))'
  			},
  			danger: {
  				DEFAULT: 'hsl(var(--danger))',
  				subtle: 'hsl(var(--danger-subtle))'
  			},
  			border: 'hsl(var(--border))',
  			input: 'hsl(var(--input))',
  			ring: 'hsl(var(--ring))',
  			chart: {
  				'1': 'hsl(var(--chart-1))',
  				'2': 'hsl(var(--chart-2))',
  				'3': 'hsl(var(--chart-3))',
  				'4': 'hsl(var(--chart-4))',
  				'5': 'hsl(var(--chart-5))'
  			}
  		},
  		keyframes: {
  			'accordion-down': {
  				from: {
  					height: '0'
  				},
  				to: {
  					height: 'var(--radix-accordion-content-height)'
  				}
  			},
  			'accordion-up': {
  				from: {
  					height: 'var(--radix-accordion-content-height)'
  				},
  				to: {
  					height: '0'
  				}
  			}
  		},
  		animation: {
  			'accordion-down': 'accordion-down 0.2s ease-out',
  			'accordion-up': 'accordion-up 0.2s ease-out'
  		}
  	}
  },
  plugins: [require("tailwindcss-animate")],
};
