// landing/src/components/LogoBand.tsx — Landing v2 design
import * as React from 'react'

const LOGOS = ['Northwind', 'Kestrel Labs', 'Meridian', 'Halcyon', 'Runway Systems', 'Basecase', 'Atlas Robotics', 'Vellum']
const TRACK = [...LOGOS, ...LOGOS] // doubled for seamless marquee loop

export function LogoBand() {
  return (
    <div className="logo-band">
      <div className="lbl">Teams shipping with Vortex</div>
      <div className="logo-track">
        {TRACK.map((name, i) => (
          <span key={i} className="logo-item">{name}</span>
        ))}
      </div>
    </div>
  )
}
