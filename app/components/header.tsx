'use client';
import { Button } from '@mui/material';
import AppBar from '@mui/material/AppBar';
import Toolbar from '@mui/material/Toolbar';
import Typography from '@mui/material/Typography';
import Link from 'next/link';

function Map() {
  return (
    <Link href="/">
          <Button variant= "text" sx={{color: 'white'}}>
                Map Dashboard
            </Button>
    </Link>
  );
}

function Live() {
  return (
    <Link href="/livepage">
          <Button variant= "text" sx={{color: 'white'}}>
                Live Feed
            </Button>
    </Link>
  );
}

function About() {
  return (
    <Link href="/about">
          <Button variant= "text" sx={{color: 'white'}}>
                About
            </Button>
    </Link>
  );
}




export default function Header() {
  return (
    <AppBar position="sticky"  sx={{ bgcolor: '#4aa054' }}>
      <Toolbar>
        <Typography fontWeight= "bold" variant="h6" component="div" sx={{ flexGrow: 1}}>
          Lime
          Aide
        </Typography>
        <div className="flex flex-row gap-8 w-full">
            <Map />
            <Live />
            <About />
        </div>
      </Toolbar>
    </AppBar>
  );
}