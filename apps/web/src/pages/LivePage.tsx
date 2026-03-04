import Typography from '@mui/material/Typography';
import Box from '@mui/material/Box';
import UpdateBoard from '../components/UpdateBoard';

export default function LivePage() {
  return (
    <main className="mx-auto w-full max-w-4xl px-8 py-8">
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 4 }}>
        <Typography variant="h5" sx={{ fontSize: '2rem', color: '#00DD00' }}>
          Live Events
        </Typography>
        <Box
          sx={{
            display: 'flex',
            alignItems: 'center',
            gap: 1,
            bgcolor: 'rgba(0, 221, 0, 0.1)',
            border: '1px solid rgba(0, 221, 0, 0.3)',
            borderRadius: '20px',
            px: 1.5,
            py: 0.5,
          }}
        >
          <Box
            sx={{
              width: 8,
              height: 8,
              borderRadius: '50%',
              bgcolor: '#00DD00',
              boxShadow: '0 0 8px #00DD00',
              animation: 'pulse 2s ease-in-out infinite',
              '@keyframes pulse': {
                '0%, 100%': { opacity: 1, boxShadow: '0 0 8px #00DD00' },
                '50%': { opacity: 0.4, boxShadow: '0 0 2px #00DD00' },
              },
            }}
          />
          <Typography variant="caption" sx={{ color: '#00DD00', fontWeight: 600, letterSpacing: 1 }}>
            LIVE
          </Typography>
        </Box>
      </Box>
      <UpdateBoard />
    </main>
  );
}
