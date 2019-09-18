import pickle
import socket
import sys
import os
import time


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

class Receiver:
    def __init__(self,receiver_port,file_name):
        self.file_name=file_name
        self.receiver_port=receiver_port
        #### parameter ##

        self.connection_socket=self.open_connection('',receiver_port)
        self.buffer_size=2048
        self.log_file='Receiver_log.txt'
        open(self.log_file, 'w').close()  # clear old log

        self.received_data=b''
        self.packet_buffer={}
        self.start_time=None
        self.init_seq_num=0
        self.nextSeqNum=None   ### sender next expected seq num; used as ack_num
        self.receiverSeqNum=None ###receiver itself seq_num
        self.sender_address=None
        self.data_received=0
        self.total_segment_received=0
        self.data_segment_received=0
        self.data_segment_with_bit_error=0
        self.duplicate_data_segment=0
        self.duplicate_ack=0
        self.is_dup_ack = False
        self.state='connecting'

    def open_connection(self,host,receiver_port):
        connection_socket=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        connection_socket.bind((host,receiver_port))
        return connection_socket

    def initiate_stp(self):

        while self.state!='established':
            if self.state=='connecting':
                ###first_handshake###
                first_hand,addr=self.connection_socket.recvfrom(self.buffer_size)
                self.start_time=time.time()
                self.sender_address=addr
                first_hand_decode=pickle.loads(first_hand)
                if first_hand_decode.syn==1:
                    packet_type = self.get_packet_type(first_hand_decode)
                    self.write_log('rcv',packet_type,first_hand_decode)
                    self.total_segment_received+=1
                    self.state='receivedSYN'

            if self.state=='receivedSYN':
                #second_handshake###
                if first_hand_decode.syn:
                    self.nextSeqNum=first_hand_decode.seq_num
                    self.receiverSeqNum=self.init_seq_num
                    second_hand=STPPacket(b'',self.receiverSeqNum,self.nextSeqNum+1,ack=True,syn=True,send_time=first_hand_decode.send_time)
                    self.connection_socket.sendto(pickle.dumps(second_hand),(self.sender_address))
                    self.write_log('snd',self.get_packet_type(second_hand),second_hand)
                    self.state='sendSYNACK'
                else:
                    sys.exit()
            if self.state=='sendSYNACK':
                #third_handshake#
                third_hand,addr=self.connection_socket.recvfrom(self.buffer_size)
                third_hand_decode=pickle.loads(third_hand)
                self.sender_address=addr
                self.receiverSeqNum = third_hand_decode.ack_num

                if third_hand_decode.ack and third_hand_decode.ack_num==self.init_seq_num+1 and third_hand_decode.seq_num==self.nextSeqNum+1:
                    self.nextSeqNum=third_hand_decode.seq_num
                    self.write_log('rcv',self.get_packet_type(third_hand_decode),third_hand_decode)
                    self.state='established'
                self.send_ack_flag = True
                self.total_segment_received+=1

    def write_log(self,packet_action,packet_type,received_packet):
        time_since_excution=time.time()-self.start_time
        with open(self.log_file,'a')as file:
            file.write('{:12} {:.2f} {:8} {:8} {:8} {:8}\n'.format(packet_action,time_since_excution,packet_type,received_packet.seq_num,len(received_packet.data),received_packet.ack_num))

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

    def receive_packet(self):
        self.total_segment_received += 1

        data,addr=self.connection_socket.recvfrom(self.buffer_size)
        self.sender_address=addr
        received_packet=pickle.loads(data)
        print('duplicate',self.duplicate_data_segment)
        if received_packet.ack==100:
            self.duplicate_data_segment+=1
            self.data_received += len(received_packet.data)


        print('stp_seq_num', received_packet.seq_num)
        if not received_packet.fin and received_packet.data is not None:
            binary_data = bin(int(received_packet.data.hex(), 16))
            self.nb_of_zero = binary_data.count('0')
            self.nb_of_one = binary_data.count('1')

            sender_nb_of_one = received_packet.nb_of_one
            sender_nb_of_zero = received_packet.nb_of_zero

        if not received_packet.fin and sender_nb_of_one != self.nb_of_one and received_packet.data is not None:
            self.data_received+=len(received_packet.data)
            self.data_segment_with_bit_error+=1
            return

        if received_packet.seq_num not in self.packet_buffer.keys() and received_packet.seq_num:
            self.packet_buffer[received_packet.seq_num]=received_packet

        packet_type=self.get_packet_type(received_packet)
        if received_packet.seq_num==self.nextSeqNum:
            while self.nextSeqNum in list(self.packet_buffer.keys()):
                cur_packet=self.packet_buffer[self.nextSeqNum]
                self.received_data += cur_packet.data
                self.data_segment_received+=1
                self.data_received+=len(cur_packet.data)

                del (self.packet_buffer[self.nextSeqNum])

                self.nextSeqNum+=len(cur_packet.data)
                # print('packet_buffer[received_packet.seq_num] {}'.format(self.packet_buffer.keys()))
            if packet_type=='F':
                self.write_log('rcv',self.get_packet_type(received_packet),received_packet)
                self.nextSeqNum = received_packet.seq_num + 1
                self.close_stp()
            if packet_type != 'F' or packet_type=='D':
                self.write_log('rcv', self.get_packet_type(received_packet),received_packet)

            if self.send_ack_flag:

                action_type = ''
                if self.is_dup_ack:
                    action_type = 'snd/DA'
                else:
                    action_type = 'snd'
                ack_packet = STPPacket(b'', self.receiverSeqNum, self.nextSeqNum, ack=True, send_time=received_packet.send_time)
                self.connection_socket.sendto(pickle.dumps(ack_packet), self.sender_address)
                self.write_log(action_type, self.get_packet_type(ack_packet), ack_packet)
                self.is_dup_ack = False

                print(self.receiverSeqNum, self.nextSeqNum)
                print('send ack\n')
        elif received_packet.seq_num<self.nextSeqNum or received_packet.seq_num in self.packet_buffer.keys():

            self.duplicate_ack+=1
            self.is_dup_ack=True
            if packet_type != 'F':
                self.write_log('rcv', self.get_packet_type(received_packet),received_packet)

            if self.send_ack_flag:
                action_type = ''
                if self.is_dup_ack:
                    action_type = 'snd/DA'
                else:
                    action_type = 'snd'
                ack_packet = STPPacket(b'', self.receiverSeqNum, self.nextSeqNum, ack=True, send_time=received_packet.send_time)
                self.connection_socket.sendto(pickle.dumps(ack_packet), self.sender_address)
                self.write_log(action_type, self.get_packet_type(ack_packet), ack_packet)
                self.is_dup_ack = False

                print(self.receiverSeqNum, self.nextSeqNum)
                print('send ack\n')
        else:
            if packet_type != 'F':
                self.write_log('rcv', self.get_packet_type(received_packet),received_packet)

            if self.send_ack_flag:
                action_type = ''
                if self.is_dup_ack:
                    action_type = 'snd/DA'
                else:
                    action_type = 'snd'
                ack_packet = STPPacket(b'', self.receiverSeqNum, self.nextSeqNum, ack=True, send_time=received_packet.send_time)
                self.connection_socket.sendto(pickle.dumps(ack_packet), self.sender_address)
                self.write_log(action_type, self.get_packet_type(ack_packet), ack_packet)
                self.is_dup_ack = False
                print(self.receiverSeqNum,    self.nextSeqNum)
                print('send ack\n')

    def close_stp(self):

        #send ack#
        ack_packet=STPPacket(b'',self.receiverSeqNum,self.nextSeqNum,ack=True)
        self.write_log('snd',self.get_packet_type(ack_packet),ack_packet)
        self.connection_socket.sendto(pickle.dumps(ack_packet),self.sender_address)

        #send fin#
        fin_packet = STPPacket(b'', self.receiverSeqNum, self.nextSeqNum, fin=True)
        self.write_log('snd', self.get_packet_type(fin_packet), fin_packet)
        self.connection_socket.sendto(pickle.dumps(fin_packet), self.sender_address)

        ##receive_ack#
        data,addr=self.connection_socket.recvfrom(self.buffer_size)
        last_packet=pickle.loads(data)
        self.sender_address=addr
        packet_type=self.get_packet_type(last_packet)

        print(last_packet.ack_num, self.init_seq_num, last_packet.seq_num, self.nextSeqNum)
        if packet_type=='A':
            if last_packet.ack_num == self.init_seq_num + 1 and last_packet.seq_num == self.nextSeqNum + 1:
                self.nextSeqNum = last_packet.seq_num

        self.write_log('rcv', self.get_packet_type(last_packet),last_packet)

        self.send_ack_flag = False
        self.total_segment_received+=1

    def close_connection(self):
        with open(self.file_name, 'wb') as file:
            file.write(self.received_data)
        self.connection_socket.close()

    def write_summary(self):
        with open(self.log_file, 'a') as file:
            file.write('=============================================================\n')
            file.write('Amount of data received (bytes)                           {}\n'.format(self.data_received))
            file.write('Total Segments Received                                   {}\n'.format(self.total_segment_received))
            file.write('Data segments received                                    {}\n'.format(self.total_segment_received-4))
            file.write('Data segments with Bit Errors                             {}\n'.format(self.data_segment_with_bit_error))
            file.write('Duplicate data segments received                          {}\n'.format(self.duplicate_data_segment))
            file.write('Duplicate ACKs sent                                       {}\n'.format(self.duplicate_ack))
            file.write('=============================================================')

if __name__=='__main__':

    nb_of_parameter=3
    print('receiver listening.........')
    if len(sys.argv)==nb_of_parameter:
        receiver_port=int(sys.argv[1])
        file_name=sys.argv[2]
    else:
        print('please enter |receiver_port, file_name| in order')
        sys.exit()
    # receiver_port=3000
    # file_name='t1.pdf'
    receiver=Receiver(receiver_port,file_name)
    receiver.initiate_stp()
    while receiver.send_ack_flag:
        receiver.receive_packet()

    receiver.close_connection()
    receiver.write_summary()
