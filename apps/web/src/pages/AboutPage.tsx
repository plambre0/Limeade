import { Typography } from '@mui/material';
import Box from '@mui/material/Box';

export default function AboutPage() {
  return (
    <main className="mx-auto w-full max-w-6xl px-8 py-8">
      <div className="flex flex-col gap-8 w-full">
        <Typography variant="h6" sx={{ fontSize: '3rem', color: '#00DD00' }}>
          About ScootSafe
        </Typography>
        <Typography sx={{ fontSize: '20px', color: '#AAAAAA' }}>
          Chicagoans love the electric scooter but without the proper data we cannot ensure that we
          are doing enough to keep them safe on them. There are plenty of safety issues that can
          arise with the use of these scooters from, reckless driving, unsafe roads, and lack of
          knowledge on the condition of the roads. Many of these incidents go unreported. We have
          set out to fix this by collecting the data and compiling it here capturing live reports of
          these issues. We hope that with this data the city can work towards helping these riders
          be safer.
        </Typography>
      </div>
      <Box sx={{ mt: 4 }}>
        <Typography sx={{ fontSize: '1.5rem', color: '#AAAAAA' }}>-Ride safe,</Typography>
        <Typography sx={{ fontSize: '2rem', color: '#00DD00', fontWeight: 600 }}>
          DePaul Demonhacks 2026 ScootSafe team!
        </Typography>
      </Box>
    </main>
  );
}
