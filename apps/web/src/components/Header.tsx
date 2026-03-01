import { Button } from '@mui/material';
import AppBar from '@mui/material/AppBar';
import Toolbar from '@mui/material/Toolbar';
import Typography from '@mui/material/Typography';
import { Link } from 'react-router-dom';

export default function Header() {
  return (
    <AppBar position="sticky" sx={{ bgcolor: '#766475' }}>
      <Toolbar>
        <Typography fontWeight="bold" variant="h6" component="div" sx={{ flexGrow: 1 }}>
          Scoot Safe
        </Typography>
        <div className="flex flex-row gap-8 w-full">
          <Link to="/">
            <Button variant="text" sx={{ color: 'white' }}>Map Dashboard</Button>
          </Link>
          <Link to="/live">
            <Button variant="text" sx={{ color: 'white' }}>Live Feed</Button>
          </Link>
          <Link to="/about">
            <Button variant="text" sx={{ color: 'white' }}>About</Button>
          </Link>
        </div>
      </Toolbar>
    </AppBar>
  );
}
