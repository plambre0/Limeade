'use client';
import { useState, useEffect } from 'react';
import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Typography from '@mui/material/Typography';

interface Event {
  id: string;
  label: string;
}

export default function UpdateBoard(){

    const [events, setEvents] = useState<Event[]>([]);

  useEffect(() => {
    const ws = new WebSocket('ws://localhost:8000/ws/ride');

    ws.onmessage = (message) => {
      const data = JSON.parse(message.data);
      setEvents(prev => [data, ...prev].slice(0, 20)); // keep last 20 events
    };

    return () => ws.close();
  }, []);

    return(
        <Box sx={{ backgroundColor: '#e3e2e4', borderRadius: 2, p: 1  }}>
            <Card variant="outlined" sx={{boxShadow: '0px 4px 12px rgba(0, 0, 0, 0.1)',
        borderRadius: '10px',
            border: '2px solid #322332'}}>
                <CardContent>
                    <Typography>
                        This is a placeholder????????????????
                        heu
                    </Typography>
                </CardContent>
            </Card>
            {events.map((event) => (
            <Card variant="outlined" sx={{boxShadow: '0px 4px 12px rgba(0, 0, 0, 0.1)',
        borderRadius: '10px',
            border: '2px solid #322332'}}>
                    <CardContent> 
                        <Typography>
                            {event.label}
                        </Typography>
                    </CardContent>
                </Card>
            ))}
        </Box>
    )
}