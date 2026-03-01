import Typography from '@mui/material/Typography';
import Box from '@mui/material/Box';

export default function Footer() {
  return (
    <Box
      component="footer"
      sx={{
        mt: 'auto',
        color: 'white',
        textAlign: 'center',
        position: "fixed"
      }}
    >
      <Typography variant="body2">
        © 2024 My App. All rights reserved.
      </Typography>
    </Box>
  );
}