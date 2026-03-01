import { useQuery } from '@tanstack/react-query';
import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Chip from '@mui/material/Chip';
import Typography from '@mui/material/Typography';

const API = 'http://localhost:8000';

interface Hazard {
  id: number;
  latitude: number;
  longitude: number;
  hazard_type: string;
  severity: number;
  description: string | null;
  source: string;
  created_at: string;
}

const severityColor: Record<number, 'success' | 'warning' | 'error'> = {
  1: 'success',
  2: 'success',
  3: 'warning',
  4: 'error',
  5: 'error',
};

export default function UpdateBoard() {
  const { data: hazards = [] } = useQuery<Hazard[]>({
    queryKey: ['hazards'],
    queryFn: () =>
      fetch(`${API}/hazards?lat=41.88&lng=-87.63&radius_km=100`).then((r) => r.json()),
    refetchInterval: 5000,
  });

  const sorted = [...hazards].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
  );

  return (
    <Box sx={{ backgroundColor: '#e3e2e4', borderRadius: 2, p: 1, maxHeight: '70vh', overflow: 'auto' }}>
      {sorted.length === 0 && (
        <Card variant="outlined" sx={{ borderRadius: '10px', border: '2px solid #322332' }}>
          <CardContent>
            <Typography color="text.secondary">
              No hazards detected yet. Start a ride to see live events.
            </Typography>
          </CardContent>
        </Card>
      )}
      {sorted.map((hazard) => (
        <Card
          key={hazard.id}
          variant="outlined"
          sx={{ borderRadius: '10px', border: '2px solid #322332', mb: 1 }}
        >
          <CardContent sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <Typography fontWeight="bold" sx={{ textTransform: 'capitalize' }}>
                {hazard.hazard_type.replace('_', ' ')}
              </Typography>
              <Chip
                label={`Severity ${hazard.severity}`}
                size="small"
                color={severityColor[hazard.severity] ?? 'default'}
              />
            </Box>
            {hazard.description && (
              <Typography variant="body2" color="text.secondary">
                {hazard.description}
              </Typography>
            )}
            <Typography variant="caption" color="text.secondary">
              {new Date(hazard.created_at).toLocaleTimeString()} &middot;{' '}
              {hazard.latitude.toFixed(4)}, {hazard.longitude.toFixed(4)}
            </Typography>
          </CardContent>
        </Card>
      ))}
    </Box>
  );
}
