import socket
import pickle
import time
import sys
import matplotlib.pyplot as plt
import random as r
from threading import Timer
import os

estimatedRTT_list=[]
devRTT_list=[]
timeout_list=[]

EstimatedRTT=0.5
DevRTT=0.25
init_gamma=0
timeout_length=0

def init_gamma_func(gamma_value):
    global timeout_length
    timeout_length=EstimatedRTT + gamma_value * DevRTT


def calculate_time(sampleRTT,gamma_value):
    global timeout_list
    global devRTT_list
    global estimatedRTT_list

    global EstimatedRTT
    # global gamma
    global DevRTT
    global timeout_length
    EstimatedRTT=(1-0.125)*EstimatedRTT+0.125*sampleRTT
    DevRTT=(1-0.25)*DevRTT+0.25*abs(sampleRTT-EstimatedRTT)
    TimeoutInterval=EstimatedRTT + gamma_value * DevRTT
    timeout_length=TimeoutInterval

    estimatedRTT_list.append(EstimatedRTT)
    devRTT_list.append(DevRTT)
    timeout_list.append(timeout_length)

class STPPacket:
    def __init__(self,data,seq_num,ack_num,ack=False,syn=False,fin=False,send_time=0,nb_of_zero=0,nb_of_one=0):
        self.data = data
        self.seq_num = seq_num
        self.ack_num = ack_num
        self.ack = ack
        self.syn = syn
        self.fin = fin
        self.send_time=send_time
        self.nb_of_zero=nb_of_zero
        self.nb_of_one=nb_of_one
        # print('send_time {}'.format(send_time))
class Sender:
    def __init__(self,receiver_host_ip,receiver_port,file_path,MWS,MSS,seed,gamma,pDrop,pDuplicate,pCorrupt,pOrder,pDelay,maxDelay,maxOrder):
        self.receiver_host_ip=receiver_host_ip
        self.receiver_port=receiver_port
        self.file_path=file_path
        self.MWS=MWS
        self.MSS=MSS
        self.seed=seed
        self.gamma=gamma
        self.pDrop=pDrop
        self.pDuplicate=pDuplicate
        self.pCorrupt=pCorrupt
        self.pOrder=pOrder
        self.pDelay=pDelay
        self.maxDelay=maxDelay
        self.maxOrder=maxOrder
        #****** parameters*******#

        self.log_file='Sender_log.txt'
        open(self.log_file, 'w').close()
        r.seed(self.seed)
        self.connection_socket=self.open_connection()
        self.syn_flag=False
        self.fin_flag=False
        self.init_seq_num=0
        self.next_seq_num=self.init_seq_num
        self.start_time=None
        self.receiver_seq_num=0
        self.sender_buffer={}
        self.is_send=False
        self.send_base=self.next_seq_num
        self.received_duplicate_ack=0
        self.sender_retransmit_timer=None
        self.timer_flag=True
        self.file_size=0
        self.segment_transmitted=0
        self.nb_dropped=0
        self.nb_corrupted=0
        self.nb_reordered=0
        self.nb_duplicated=0
        self.nb_delayed=0
        self.nb_retransmit_timeout=0;
        self.nb_fast_transmit=0
        self.nb_duplicate_ack=0
        self.nb_pld=0
        self.SampleRTT=0
        self.delay_timer=None
        self.porder_packet=None
        self.porder_count=0
        self.porder_flag=False
        self.retransmit_packet_list=[]
        self.sampleRTT_list=[]
        self.devRTT_list=[]
        self.estimateRTT_list=[]
        self.timeout_list=[]
        self.receiver_detail=(self.receiver_host_ip,self.receiver_port)

    def open_connection(self):
        connection_socket=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        return connection_socket

    def establish_connection(self):
        global init_gamma
        init_gamma=self.gamma

        init_gamma_func(init_gamma)

        self.start_time=time.time()
        ####first handshake###
        self.syn_flag=True
        init_packet=STPPacket(b'',self.init_seq_num,0,syn=True)
        self.next_seq_num+=1
        self.connection_socket.sendto(pickle.dumps(init_packet),self.receiver_detail)
        action_type='snd'
        send_type=self.get_packet_type(init_packet)
        self.write_log(action_type, send_type, init_packet)
        self.segment_transmitted+=1

        ###second handshake###
        second_hand,address=self.connection_socket.recvfrom(2048)
        second_hand_decode=pickle.loads(second_hand)
        if second_hand_decode.syn and second_hand_decode.ack:
            self.receiver_seq_num=second_hand_decode.seq_num
            self.write_log('rcv', self.get_packet_type(second_hand_decode),second_hand_decode)
            self.send_base = second_hand_decode.ack_num

        else:
            sys.exit()

        ###third handshake##
        self.receiver_seq_num+=1
        third_hand=STPPacket(b'',self.next_seq_num,self.receiver_seq_num,ack=True)
        self.connection_socket.sendto(pickle.dumps(third_hand),self.receiver_detail)
        action_type='snd'
        send_type=self.get_packet_type(third_hand)
        self.write_log(action_type,send_type,third_hand)
        self.syn_flag=False
        self.segment_transmitted+=1




    def write_log(self,packet_action,packet_type,sender_packet):
        gap=time.time()-self.start_time

        with open(self.log_file,'a')as handle:
            handle.write('{:12} {:.2f} {:8} {:8} {:8} {:8}\n'.format(packet_action,gap,packet_type,sender_packet.seq_num,len(sender_packet.data),sender_packet.ack_num))

    def get_packet_type(self,sender_packet):
        type=''
        if len(sender_packet.data)>0:
            type='D'
        elif sender_packet.fin==1:
            type='F'
        elif sender_packet.ack==1:
            type='A'
        elif sender_packet.syn==1:
            type='S'
        return type


    def read_file(self,file_name):
        if os.path.exists(file_name):
            with open(file_name, 'rb') as file:
                self.current_file_length = list(file.read())
        else:
            print('file does not exist')
            sys.exit()

    def current_window_length(self):
        if self.next_seq_num-self.send_base>0:
            return self.next_seq_num-self.send_base
        else:
            return 0

    def packaging_packet(self):
        data_size=0
        if self.MWS>self.MSS:
            temp=self.MWS-self.current_window_length()
            if temp>0 and temp>self.MSS:
                data_size= self.MSS
            elif temp>0:
                data_size= temp
            else:
                print('cur window error')
        else:
            data_size=self.MWS

        if data_size>0:
            packet_bytes=self.current_file_length[:data_size]
            file_length=len(self.current_file_length)
            self.current_file_length=self.current_file_length[data_size:file_length]
            packet_data=bytes(packet_bytes)
            packet=STPPacket(packet_data,self.next_seq_num,self.receiver_seq_num,send_time=time.time())
        else:
            print('packing packet error')
            sys.exit()
        return packet

    def send_packet(self,sender_packet):
        self.segment_transmitted += 1

        if self.sender_retransmit_timer is None:
            self.set_sender_retransmit_timer()
            self.sender_retransmit_timer.start()

        self.received_duplicate_ack=0
        send_type=self.get_packet_type(sender_packet)
        self.sender_buffer[sender_packet.seq_num]=sender_packet

        binary_data = bin(int(sender_packet.data.hex(), 16))
        nb_of_zero = binary_data.count('0')
        nb_of_one = binary_data.count('1')
        sender_packet.nb_of_one = nb_of_one
        sender_packet.nb_of_zero = nb_of_zero

        if self.porder_count==self.maxOrder and self.porder_flag:
            print('porder_send', self.porder_packet.seq_num)
            action_type='snd/rord'
            self.connection_socket.sendto(pickle.dumps(self.porder_packet), self.receiver_detail)
            self.porder_flag=False
            self.porder_count=0
            self.write_log(action_type,self.get_packet_type(self.porder_packet),self.porder_packet)
            print('snd/rord', self.porder_packet.seq_num)

        if r.random()<self.pDrop:
            self.next_seq_num += len(sender_packet.data)
            print('drop')
            action_type='drop'
            self.nb_dropped+=1

            self.write_log(action_type, send_type, sender_packet)
            if self.porder_flag:
                self.porder_count += 1


        elif r.random()<self.pDuplicate:
            print('duplicate')
            self.segment_transmitted+=1

            self.next_seq_num += len(sender_packet.data)

            action_type='snd/dup'
            self.connection_socket.sendto(pickle.dumps(sender_packet),self.receiver_detail)
            sender_packet.ack=100
            self.connection_socket.sendto(pickle.dumps(sender_packet),self.receiver_detail)

            print('duplicate_packet_seq_num {}'.format(sender_packet.seq_num))

            duplicate_action_type='snd'
            self.write_log(duplicate_action_type,send_type,sender_packet)
            self.write_log(action_type, send_type, sender_packet)
            self.nb_duplicated+=1
            if self.porder_flag:
                self.porder_count += 1

        elif r.random()<self.pCorrupt:
            print('corrupt')

            self.next_seq_num += len(sender_packet.data)

            action_type='snd/corr'
            error_nb_of_zero=nb_of_zero+1
            error_nb_of_one=nb_of_one-1
            sender_packet.nb_of_one=error_nb_of_one
            sender_packet.nb_of_zero=error_nb_of_zero
            print('corrupt_seq_num: ',sender_packet.seq_num)

            self.connection_socket.sendto(pickle.dumps(sender_packet),self.receiver_detail)
            self.write_log(action_type, send_type, sender_packet)
            self.nb_corrupted+=1
            if self.porder_flag:
                self.porder_count += 1

        elif r.random()<self.pOrder:
            self.next_seq_num += len(sender_packet.data)

            if self.porder_count==0 and not self.porder_flag:
                self.porder_packet=sender_packet
                self.porder_flag=True
                print('porder0')

            elif self.porder_flag:
                print('porder1')

                action_type='snd'
                self.connection_socket.sendto(pickle.dumps(sender_packet),self.receiver_detail)
                self.write_log(action_type,self.get_packet_type(sender_packet),sender_packet)
                if self.porder_flag:
                    self.porder_count += 1

            self.nb_reordered+=1

        elif r.random()<self.pDelay:
            print('pdelay')
            self.next_seq_num += len(sender_packet.data)
            if self.maxDelay!=0:
                delay_time = (r.random()*self.maxDelay)/1000
            else:
                delay_time=0
            self.set_delay_timer(delay_time, sender_packet)
            self.delay_timer.start()
            action_type = 'snd/delay'
            self.write_log(action_type, send_type, sender_packet)
            self.nb_delayed+=1

            if self.porder_flag:
                self.porder_count += 1
        else:
            print('common send', sender_packet.seq_num)
            self.next_seq_num += len(sender_packet.data)
            action_type = 'snd'
            sender_packet.nb_of_zero=nb_of_zero
            sender_packet.nb_of_one=nb_of_one
            self.connection_socket.sendto(pickle.dumps(sender_packet), self.receiver_detail)
            self.write_log(action_type, send_type, sender_packet)
            if self.porder_flag:
                self.porder_count += 1

        self.nb_pld += 1
        print('porder_count', self.porder_count)

    def draw_plot(self):
        plt.subplot(211)
        t_plt, = plt.plot(estimatedRTT_list)
        v_plt, = plt.plot(devRTT_list)
        plt.title('Parameters related to timeout')

        plt.ylabel('Time(s)')
        plt.legend((t_plt, v_plt), ('ERTT', 'DRTT'))


        plt.subplot(212)
        z_plt, = plt.plot(timeout_list)
        x_plt, =plt.plot(self.sampleRTT_list)
        plt.xlabel('number of times')
        plt.ylabel('Time(s)')
        plt.legend((z_plt, x_plt), ('Timeout', 'SampleRTT'))

        # plt.legend(x_plt,'SampleRTT')
        # print(estimatedRTT_list)
        # print(devRTT_list)
        # print(timeout_list)
        # print(self.sampleRTT_ligt)
        plt.savefig('Timeout.png')
        plt.show()

    def receive_packet(self):

        if self.sender_retransmit_timer is not None:
            self.sender_retransmit_timer.cancel()
        if len(self.sender_buffer) > 0 :
            self.set_sender_retransmit_timer()
            self.sender_retransmit_timer.start()

        data,address=self.connection_socket.recvfrom(2048)
        packet_data=pickle.loads(data)
        received_ack=packet_data.ack_num
        if packet_data.ack>0:
            if received_ack>self.send_base:
                # print(self.retransmit_packet_list)

                # calculate_SampleRTT_flag=True
                # for i in range(int(self.MWS/self.MSS)):
                #     if received_ack-i*self.MSS in self.retransmit_packet_list:
                #         calculate_SampleRTT_flag=False
                #         break
                #
                #
                #
                # if received_ack-self.send_base==self.MSS and calculate_SampleRTT_flag:
                #     print(time.time(), sender_packet.send_time)
                #     self.SampleRTT=time.time()-sender_packet.send_time
                #     calculate_time(self.SampleRTT,self.gamma)
                #     print('sampleRTT ',self.SampleRTT)
                # else:
                #     print(self.retransmit_packet_list, sender_packet.ack_num)

                if packet_data.send_time!=0:

                    self.SampleRTT = time.time() - packet_data.send_time

                    self.sampleRTT_list.append(self.SampleRTT)

                    calculate_time(self.SampleRTT,self.gamma)

                self.send_base=received_ack


                removed_keys=[]
                for key in self.sender_buffer.keys():
                    if key < self.send_base:
                        removed_keys.append(key)

                self.received_duplicate_ack = 0
                self.write_log('rcv',self.get_packet_type(packet_data),packet_data)
                if len(removed_keys)!=0:
                    for value in removed_keys:
                        del (self.sender_buffer[value])

                if self.sender_retransmit_timer is not None:
                    self.sender_retransmit_timer.cancel()
                if len(self.sender_buffer) > 0:
                    self.set_sender_retransmit_timer()
                    self.sender_retransmit_timer.start()
            else:

                self.received_duplicate_ack+=1
                self.nb_duplicate_ack+=1
                packet_type=self.get_packet_type(packet_data)
                self.write_log('rcv/DA',packet_type,packet_data)

                if self.received_duplicate_ack==3:
                    self.retransmit_packet(self.send_base)
                    self.received_duplicate_ack=0

    def retransmit_packet(self,seq_num,cause=None):
        self.segment_transmitted += 1

        if cause=='timeout':
            self.nb_retransmit_timeout+=1

        retransmit_packet=self.sender_buffer[seq_num]
        retransmit_packet.send_time=0

        binary_data = bin(int(retransmit_packet.data.hex(), 16))
        nb_of_zero = binary_data.count('0')
        nb_of_one = binary_data.count('1')
        retransmit_packet.nb_of_one = nb_of_one
        retransmit_packet.nb_of_zero = nb_of_zero

        if self.porder_count==self.maxOrder and self.porder_flag:
            print('porder_send', self.porder_packet.seq_num)
            action_type='snd/rord'
            self.connection_socket.sendto(pickle.dumps(self.porder_packet),self.receiver_detail)
            self.porder_flag=False
            self.porder_count=0
            self.write_log(action_type,self.get_packet_type(self.porder_packet),self.porder_packet)
            print('snd/rord', self.porder_packet.seq_num)


        action_type=''
        if r.random()<self.pDrop:
            action_type='drop'
            self.write_log(action_type, self.get_packet_type(retransmit_packet), retransmit_packet)
            self.nb_dropped+=1
            if self.porder_flag:
                self.porder_count += 1

        elif r.random()<self.pDuplicate:
            self.segment_transmitted+=1

            action_type = 'snd/dup'
            self.connection_socket.sendto(pickle.dumps(retransmit_packet), self.receiver_detail)
            retransmit_packet.ack=100

            self.connection_socket.sendto(pickle.dumps(retransmit_packet), self.receiver_detail)
            duplicate_action_type = 'snd'
            self.write_log(duplicate_action_type, self.get_packet_type(retransmit_packet), retransmit_packet)

            self.write_log(action_type, self.get_packet_type(retransmit_packet), retransmit_packet)
            self.nb_duplicated+=1
            if self.porder_flag:
                self.porder_count += 1

        elif r.random()<self.pCorrupt:
            action_type = 'snd/corr'
            error_nb_of_zero = nb_of_zero + 1
            error_nb_of_one = nb_of_one - 1
            retransmit_packet.nb_of_one = error_nb_of_one
            retransmit_packet.nb_of_zero = error_nb_of_zero
            self.connection_socket.sendto(pickle.dumps(retransmit_packet), self.receiver_detail)
            self.write_log(action_type, self.get_packet_type(retransmit_packet), retransmit_packet)
            self.nb_corrupted+=1
            if self.porder_flag:
                self.porder_count += 1

        elif r.random()<self.pOrder:
            if self.porder_count==0 and not self.porder_flag:
                self.porder_packet=retransmit_packet
                self.porder_flag=True
            elif self.porder_flag:
                action_type='snd'
                self.connection_socket.sendto(pickle.dumps(retransmit_packet),self.receiver_detail)
                self.write_log(action_type,self.get_packet_type(retransmit_packet),retransmit_packet)
                if self.porder_flag:
                    self.porder_count += 1
            self.nb_reordered+=1

        elif r.random()<self.pDelay:
            if self.maxDelay!=0:
                delay_time = (r.random()*self.maxDelay)/1000
            else:
                delay_time=0
            self.set_delay_timer(delay_time, retransmit_packet)
            self.delay_timer.start()
            action_type = 'snd/delay'
            self.write_log(action_type, self.get_packet_type(retransmit_packet), retransmit_packet)
            self.nb_delayed+=1
            if self.porder_flag:
                self.porder_count += 1
        else:
            print('retransmit send', retransmit_packet.seq_num)

            retransmit_packet.nb_of_one=nb_of_one
            retransmit_packet.nb_of_zero=nb_of_zero
            self.connection_socket.sendto(pickle.dumps(retransmit_packet),self.receiver_detail)
            action_type = 'snd/RXT'
            if cause != 'timeout':
                self.nb_fast_transmit += 1
            self.retransmit_packet_list.append(retransmit_packet.seq_num)
            self.write_log(action_type, self.get_packet_type(retransmit_packet), retransmit_packet)
            if self.porder_flag:
                self.porder_count += 1

        self.nb_pld += 1


        print('porder_count', self.porder_count)



        self.set_sender_retransmit_timer()
        self.sender_retransmit_timer.start()
        self.is_send=False

    def set_sender_retransmit_timer(self):
        print('set timer')
        if self.sender_retransmit_timer is not None:
            self.sender_retransmit_timer.cancel()
        if self.timer_flag:
            self.sender_retransmit_timer = Timer(timeout_length,self.retransmit_packet,args=[self.send_base,'timeout'])

    def set_delay_timer(self,delay_time,sender_packet):
        if self.timer_flag:
            self.delay_timer = Timer(delay_time,self.send_delay_packet,args=[sender_packet])

    def send_delay_packet(self,sender_packet):
        if self.sender_retransmit_timer is None:
            self.set_sender_retransmit_timer()
            self.sender_retransmit_timer.start()
        # self.next_seq_num += len(sender_packet.data)
        # send_type = self.get_packet_type(sender_packet)
        # self.sender_buffer[sender_packet.seq_num] = sender_packet
        self.connection_socket.sendto(pickle.dumps(sender_packet), self.receiver_detail)

    def close_connection(self):
        if self.sender_retransmit_timer is not None:
            self.sender_retransmit_timer.cancel()
        if self.delay_timer is not None:
            self.delay_timer.cancel()
        ###send fin###
        self.fin_flag=True
        first_packet=STPPacket(b'',self.next_seq_num,self.receiver_seq_num,fin=True)
        self.connection_socket.sendto(pickle.dumps(first_packet),self.receiver_detail)
        self.write_log('snd', self.get_packet_type(first_packet), first_packet)

        self.segment_transmitted+=1

        ###receive ack###
        data,address=self.connection_socket.recvfrom(2048)
        second_packet=pickle.loads(data)
        if second_packet.ack and not second_packet.fin:
            self.write_log('rcv',self.get_packet_type(second_packet),second_packet)

        ##receive fin##
        if second_packet.ack:
            data,address=self.connection_socket.recvfrom(2048)
            third_packet=pickle.loads(data)
            self.write_log('rcv',self.get_packet_type(third_packet),third_packet)

        ##send ack##
        self.receiver_seq_num=third_packet.seq_num+1
        self.next_seq_num=third_packet.ack_num
        fourth_packet = STPPacket(b'', self.next_seq_num, self.receiver_seq_num, ack=True)
        self.connection_socket.sendto(pickle.dumps(fourth_packet),self.receiver_detail)
        self.write_log('snd',self.get_packet_type(fourth_packet),fourth_packet)
        self.fin_flag=False
        self.segment_transmitted+=1


    def write_summary(self):
        with open(self.log_file,'a') as file:
            file.write('=============================================================\n')
            file.write('Size of the file (in Bytes)                               {}\n'.format(self.file_size))
            file.write('Segments transmitted (including drop & RXT)               {}\n'.format(self.segment_transmitted))
            file.write('Number of Segments handled by PLD                         {}\n'.format(self.segment_transmitted-4))
            file.write('Number of Segments dropped                                {}\n'.format(self.nb_dropped))
            file.write('Number of Segments Corrupted                              {}\n'.format(self.nb_corrupted))
            file.write('Number of Segments Re-ordered                             {}\n'.format(self.nb_reordered))
            file.write('Number of Segments Duplicated                             {}\n'.format(self.nb_duplicated))
            file.write('Number of Segments Delay                                  {}\n'.format(self.nb_delayed))
            file.write('Number of Segments Retransmissions due to TIMEOUT         {}\n'.format(self.nb_retransmit_timeout))
            file.write('Number of Segments FAST RETRANSMISSION                    {}\n'.format(self.nb_fast_transmit))
            file.write('Number of Segments DUP ACKS received                      {}\n'.format(self.nb_duplicate_ack))
            file.write('=============================================================')


if __name__=='__main__':

    nb_of_parameter=15
    if len(sys.argv)==nb_of_parameter:
        receiver_host_ip=sys.argv[1]
        receiver_port=int(sys.argv[2])
        file_path=sys.argv[3]
        MWS = int(sys.argv[4])
        MSS = int(sys.argv[5])
        gamma = int(sys.argv[6])
        pDrop = float(sys.argv[7])
        pDuplicate = float(sys.argv[8])
        pCorrupt = float(sys.argv[9])
        pOrder = float(sys.argv[10])
        maxOrder=int(sys.argv[11])
        pDelay = float(sys.argv[12])
        maxDelay=int(sys.argv[13])
        seed = int(sys.argv[14])

    else:
        print('please enter |receiver_host_ip, receiver_port, file.pdf, MWS, MSS, gamma, pDrop, Duplicate, pCorrupt, pOrder, maxOrder, pDelay, maxDelay, seed| in order')
        sys.exit()


    # file_path = 'test0.pdf'
    # MWS = 600
    # MSS = 150
    # seed = 100
    # gamma = 4
    # pDrop = 0.1
    # pDuplicate = 0
    # pCorrupt = 0
    # pOrder = 0
    # pDelay = 0
    # maxDelay = 50
    # maxOrder = 4

    sender=Sender(receiver_host_ip,receiver_port,file_path,MWS,MSS,seed,gamma,pDrop,pDuplicate,pCorrupt,pOrder,pDelay,maxDelay,maxOrder)
    sender.read_file(file_path)

    sender.establish_connection()
    while True:
        if len(sender.current_file_length) > 0 or len(sender.sender_buffer) > 0:
            sender.is_send = True
            while (MWS - sender.current_window_length()) > 0 and len(sender.current_file_length) > 0:
                cur_packet=sender.packaging_packet()
                sender.file_size+=len(cur_packet.data)
                sender.send_packet(cur_packet)

                sender.is_send=False

            sender.receive_packet()
        else:
            break

    sender.close_connection()
    sender.write_summary()
    # sender.draw_plot()






