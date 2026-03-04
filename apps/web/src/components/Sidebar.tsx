import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import { Typography } from '@mui/material';

export default function Sidebar() {
  return (
    <Card
      variant="outlined"
      sx={{
        boxShadow: '0px 4px 12px rgba(0, 0, 0, 0.4)',
        borderRadius: '10px',
        border: '1px solid #333',
        bgcolor: '#111111',
        paddingBottom: '80px',
        transition: 'transform 0.2s ease, border-color 0.2s ease',
        '&:hover': { transform: 'scale(1.02)', borderColor: '#00DD00', cursor: 'pointer' },
      }}
    >
      <CardContent>
        <Typography gutterBottom variant="h5" component="div">
          Incident information
        </Typography>
        <Typography>This is the demo card for information on a site</Typography>
      </CardContent>
    </Card>
  );
}
