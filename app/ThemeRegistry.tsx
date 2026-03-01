'use client';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import CssBaseline from '@mui/material/CssBaseline';
import { Zalando_Sans_SemiExpanded } from 'next/font/google';

const poppins = Zalando_Sans_SemiExpanded({ subsets: ['latin'], weight: ['900','700'] });

const theme = createTheme({
  typography: { fontFamily: poppins.style.fontFamily,},
  components: {
    MuiChip: {
      styleOverrides: {
        root: ({ theme }) => ({
          variants: [
            {
              props: { variant: 'outlined', color: 'primary' },
              style: {
                backgroundColor: `rgba(${theme.vars.palette.primary.mainChannel} / 0.12)`,
              },
            },
          ],
        }),
      },
    },
  },
});
// customize here

export default function ThemeRegistry({ children }: { children: React.ReactNode }) {
  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      {children}
    </ThemeProvider>
  );
}