"""Forward-only event processing with bounded temporal state."""
from collections import deque
import math

from event_processor import EventProcessor


class StreamingProcessor:
    def __init__(self, config, sensor_size):
        self.config = None
        self.configuration_generation = 0
        self.configure(config,sensor_size)

    def configure(self, config, sensor_size):
        settings=dict(config)
        capacity=settings.pop('window_capacity',100_000)
        if type(capacity) is not int or not 1 <= capacity <= 1_000_000:
            raise ValueError('Window capacity must be an integer in [1,1000000]')
        validated=EventProcessor(settings,sensor_size)
        next_config=dict(validated.config,window_capacity=capacity)
        display_keys={'gain','normalization'}
        clear=(self.config is None or self.sensor_size != tuple(sensor_size) or
               any(self.config[key]!=next_config[key] for key in next_config if key not in display_keys))
        self.config=next_config
        self.sensor_size=tuple(sensor_size)
        x0,y0,x1,y1=self.config['roi'];b=self.config['bin_size']
        self.dimensions=((x1-x0+b-1)//b,(y1-y0+b-1)//b)
        if clear:
            previous_clock=getattr(self,'clock_ns',-1)
            self.reset()
            self.clock_ns=previous_clock
            self.configuration_generation+=1

    def reset(self):
        cells=self.dimensions[0]*self.dimensions[1]
        self.on=[0]*cells;self.off=[0]*cells
        self.last_on=[-1]*cells;self.last_off=[-1]*cells
        self.window=deque()
        self.clock_ns=-1
        self.incoming_count=self.roi_count=self.selected_count=0
        self.window_overflow_count=0

    def advance(self, cursor_ns):
        if type(cursor_ns) is not int or not max(0,self.clock_ns) <= cursor_ns <= 2**63-1:
            raise ValueError('Streaming clock cannot move backward')
        if self.config['representation']=='window':
            boundary=cursor_ns-self.config['window_ns']
            while self.window and self.window[0][0] <= boundary:
                _,index,p=self.window.popleft()
                output=self.on if p==1 else self.off
                output[index]-=1
        self.clock_ns=cursor_ns

    def consume(self, events):
        previous=max(0,self.clock_ns)
        for row in events:
            if len(row)!=4 or any(type(v) is not int for v in row):
                raise ValueError('Events must be four integer fields')
            x,y,t,p=row
            if not (0<=x<self.sensor_size[0] and 0<=y<self.sensor_size[1]
                    and previous<=t<=2**63-1 and p in (-1,1)):
                raise ValueError('Invalid, late, or unsorted event')
            previous=t
        x0,y0,x1,y1=self.config['roi'];b=self.config['bin_size']
        for x,y,t,p in events:
            self.advance(t)
            self.incoming_count+=1
            if not (x0<=x<x1 and y0<=y<y1):continue
            self.roi_count+=1
            if self.config['polarity']=='on' and p<0 or self.config['polarity']=='off' and p>0:continue
            self.selected_count+=1
            index=((y-y0)//b)*self.dimensions[0]+(x-x0)//b
            output=self.on if p==1 else self.off
            latest=self.last_on if p==1 else self.last_off
            if self.config['representation']=='window':
                if len(self.window)==self.config['window_capacity']:
                    self.window_overflow_count+=1
                    continue
                self.window.append((t,index,p));output[index]+=1
            elif self.config['representation']=='decay':
                output[index]=(output[index]*math.exp(-(t-latest[index])/self.config['tau_ns'])
                               if latest[index]>=0 else 0)+1
            latest[index]=t

    def snapshot(self, cursor_ns):
        self.advance(cursor_ns)
        representation=self.config['representation']
        if representation=='window':
            on,off=list(self.on),list(self.off)
        else:
            on=[(value if representation=='decay' else 1)*math.exp(-(cursor_ns-t)/self.config['tau_ns'])
                if t>=0 else 0 for value,t in zip(self.on,self.last_on)]
            off=[(value if representation=='decay' else 1)*math.exp(-(cursor_ns-t)/self.config['tau_ns'])
                 if t>=0 else 0 for value,t in zip(self.off,self.last_off)]
        x0,y0,x1,y1=self.config['roi'];b=self.config['bin_size']
        width,height=self.dimensions
        return dict(dimensions=[width,height],origin=[x0,y0],bin_size=b,on=on,off=off,
                    bin_areas=[min(b,x1-x0-x*b)*min(b,y1-y0-y*b) for y in range(height) for x in range(width)],
                    cursor_ns=cursor_ns,representation=representation,normalization=self.config['normalization'],
                    received_count=self.incoming_count,incoming_count=self.incoming_count,
                    roi_count=self.roi_count,polarity_count=self.selected_count,selected_count=self.selected_count,
                    visible_count=len(self.window) if representation=='window' else self.selected_count,
                    resident_event_count=len(self.window),window_capacity=self.config['window_capacity'],
                    window_overflow_count=self.window_overflow_count,
                    complete_since_reset=self.window_overflow_count==0,
                    configuration_generation=self.configuration_generation,state_cells=4*width*height)
