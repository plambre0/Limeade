import { Typography } from "@mui/material";
import {Box} from "@mui/material";

export default function AboutPage(){
    return(

        <div className="flex min-h-screen items-center justify-center bg-zinc-50 font-sans">
            <main className="flex min-h-screen w-full max-w-6xl flex-col items-center justify-between py-16 px-8 sm:items-start">
                <div className="flex flex-row gap-8 w-full">
                    <Typography variant="h6" sx={{ fontSize: '3rem' }}>
                        About ScootSafe
                    </Typography>
                    <Typography sx={{ fontSize: '20px', p: "20px"}}>
                        Chicagoans love the electric scooter but without the proper data we cannot ensure that we are doing enough to keep them safe on them. There are plenty of safety issues that can arise with the use of these scooters from, reckless driving, unsafe roads, and lack of knowledge on the condition of the roads. Many of these incidents go unreported. We have set out to fix this by collecting the data and compling it here capturing live reports of these issues. We hope that with this data the city can work towards helping these riders be safer.
                    </Typography>

                </div>
        </main>
            <Box sx={{ p: "20px"}}>
            <Typography sx={{ fontSize: '1.5 rem' }}> -Ride safe,</Typography>
            <Typography sx={{ fontSize: '2rem' }}>Depaul Demonhacks 2026 ScootSafe team!</Typography>
            </Box>
        </div>


    )
}