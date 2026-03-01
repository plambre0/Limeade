'use client';
import Typography from '@mui/material/Typography';
import UpdateBoard from './components/updateboard';
import { Fade } from '@mui/material';


export default function LivePage(){
    return(
        <div className="flex min-h-screen items-center justify-center bg-zinc-50 font-sans">
            <main className="flex min-h-screen w-full max-w-6xl flex-col items-center justify-between py-16 px-8 sm:items-start">
                <div className="flex flex-row gap-8 w-full">
                    <div className= "flex-[1]">
                    <Fade in = {true} timeout= {1000} >
                        <Typography variant="h6" sx={{ fontSize: '3rem' }}>
                            Live Events
                        </Typography>
                    </Fade>
                    </div>
                    <div className = "flex-[2]">
                        <UpdateBoard />
                    </div>
                </div>
            </main>
        </div>
    )
    
}